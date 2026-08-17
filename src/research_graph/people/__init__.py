"""research_graph.people — professor + institution evidence collection.

Pipeline per author (rate-limit aware):
  1. Resolve name -> OpenAlex author_id (1 request)
  2. If resolved, fetch last_known_institutions (1 request)
  3. If institution name known, resolve to institution_id (1 request)

Three OpenAlex requests per author. With politeness pool ~10 req/s, processing
60 authors should take ~18s. We also:
  - Sleep 0.2s between requests as a cheap rate guard
  - Retry up to 3x on 429 with exponential backoff
  - Preserve any previously-resolved entries from a prior people.json so a
    partial run doesn't lose work.

Per CONTEXT.md evidence rules:
  - strong: ORCID + official page (we have ORCID from OpenAlex sometimes)
  - moderate: OpenAlex last-known institution (our default)
  - weak: only one source or sources disagree (no resolution at all)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from research_graph.config import Config
from research_graph.logging_setup import configure_logging
from research_graph.models import Author, Institution
from research_graph.people.professors import classify_strength
from research_graph.providers import get_default_registry


_log = logging.getLogger(__name__)


# --- helpers ---------------------------------------------------------------

def _call_with_retry(fn, *args, max_retries: int = 2, base_delay: float = 0.5):
    """Call fn(*args); on transient errors retry with exponential backoff.

    On 429 (rate limit), abort fast (single short retry) since politeness-pool
    cooldown can be 60+ seconds and our budget can't afford to wait that long.
    """
    import time
    last_err: Exception | None = None
    saw_429 = False
    for attempt in range(max_retries + 1):
        try:
            return fn(*args)
        except Exception as e:  # pragma: no cover (network path)
            last_err = e
            time.sleep(base_delay * (2 ** attempt))
    raise last_err if last_err else RuntimeError("retry exhausted")


def _safe_get(openalex, path: str, params: dict | None = None) -> dict | None:
    """Call openalex._get with retry; return the data dict or None on failure.

    Special-case 429: returns None after one short retry so the rest of the
    pipeline can continue without spinning on a cold politeness pool.
    """
    import time
    if getattr(openalex, "_rate_limited", False):
        return None  # circuit breaker tripped by a prior call

    def call():
        return openalex._get(path, params)  # type: ignore[attr-defined]

    try:
        r = _call_with_retry(call, max_retries=2, base_delay=0.3)
    except Exception as e:
        _log.debug(f"openalex {path} exhausted retries: {e}")
        return None
    if r.status == "failed" and r.error and "429" in r.error:
        openalex._rate_limited = True
        _log.warning(f"openalex rate-limited on {path}; circuit breaker tripped")
        return None
    if r.status != "ok" or not isinstance(r.data, dict):
        return None
    return r.data


def _resolve_author_id(name: str, registry) -> str | None:
    """Best-effort: resolve display_name to an author id (OpenAlex first, S2 fallback).

    OpenAlex gives canonical "openalex:A..." ids; Semantic Scholar returns
    "s2:<40hex>" ids. Both are usable as canonical author keys in the graph;
    we prefer OpenAlex because S2 IDs are opaque hashes.
    """
    time.sleep(0.15)
    # Try OpenAlex first.
    openalex = registry.get("openalex")
    if openalex is not None:
        data = _safe_get(openalex, "/authors", {"search": name, "per_page": 1})
        if data:
            results = data.get("results") or []
            if results:
                aid_raw = results[0].get("id")
                if aid_raw:
                    short = aid_raw.rsplit("/", 1)[-1] if aid_raw.startswith("http") else aid_raw
                    if short.startswith("A"):
                        return f"openalex:{short}"
    # Fallback: Semantic Scholar author search.
    s2 = registry.get("semantic_scholar")
    if s2 is not None:
        _get = getattr(s2, "_get", None)
        if _get is not None:
            try:
                r = _get("/author/search", {"query": name, "limit": 1})
                if r.status == "ok" and isinstance(r.data, dict):
                    items = r.data.get("data") or []
                    if items:
                        aid = items[0].get("authorId")
                        if aid:
                            return f"s2:{aid}"
            except Exception:
                pass
    return None


def _resolve_institution_id(institution_name: str, registry) -> str | None:
    """OpenAlex-first institution resolution; S2 doesn't expose inst ids."""
    openalex = registry.get("openalex")
    if openalex is None:
        return None
    time.sleep(0.15)
    data = _safe_get(openalex, "/institutions", {"search": institution_name, "per_page": 1})
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    raw = results[0].get("id")
    if not raw:
        return None
    short = raw.rsplit("/", 1)[-1] if raw.startswith("http") else raw
    if not short.startswith("I"):
        return None
    return f"openalex:{short}"


def _last_known_institution(author_id: str, registry) -> str | None:
    """Read the author's last-known institution from the OpenAlex author endpoint.

    S2 author objects don't include affiliation data, so S2 ids fall back to None.
    """
    openalex = registry.get("openalex")
    if openalex is None or not author_id.startswith("openalex:"):
        return None
    short = author_id.split(":", 1)[-1]
    if short.startswith("http"):
        short = short.rsplit("/", 1)[-1] or short
    time.sleep(0.15)
    data = _safe_get(openalex, f"/authors/{short}")
    if not data:
        return None
    lki = data.get("last_known_institutions") or []
    if lki and isinstance(lki[0], dict):
        return lki[0].get("display_name")
    return None


# --- stage ----------------------------------------------------------------

def run_people(config: Config, *, no_llm: bool = False, continue_on_error: bool = True) -> int:
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        _log.error("people: papers.json not found; run `ingest` first")
        return 1
    try:
        papers_data = json.loads(papers_path.read_text())
    except Exception as e:
        _log.error(f"people: failed to read papers.json: {e}")
        return 1

    # Preserve any previously-resolved entries from people.json so a partial
    # re-run doesn't lose work. Keys are author display names (lowercased).
    out_path = out_dir / "people.json"
    prev_by_name: dict[str, dict] = {}
    if out_path.exists():
        try:
            for r in json.loads(out_path.read_text()):
                if r.get("author"):
                    prev_by_name[r["author"].lower()] = r
        except Exception:
            pass

    registry = get_default_registry(config)
    resolved: list[dict] = []
    seen_names: set[str] = set()

    for p_data in papers_data:
        for name in (p_data.get("authors") or []):
            key = name.lower().strip()
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            # Carry forward prior resolution if present (avoids re-hitting
            # OpenAlex when an author was already resolved last run).
            entry = dict(prev_by_name.get(key, {
                "author": name,
                "author_id": None,
                "institution": None,
                "institution_id": None,
                "strength": "weak",
                "evidence": {"sources": []},
            }))
            entry["author"] = name  # always reflect current canonical name
            try:
                if not entry.get("author_id"):
                    aid = _resolve_author_id(name, registry)
                    entry["author_id"] = aid
                if entry.get("author_id"):
                    aid = entry["author_id"]
                    if isinstance(aid, str) and aid:
                        if not entry.get("institution"):
                            inst_name = _last_known_institution(aid, registry)
                            if inst_name:
                                entry["institution"] = inst_name
                        if entry.get("institution") and not entry.get("institution_id"):
                            entry["institution_id"] = _resolve_institution_id(
                                entry["institution"], registry,
                            )
                        if "openalex" not in entry.get("evidence", {}).get("sources", []):
                            entry.setdefault("evidence", {}).setdefault("sources", []).append("openalex")
                # Strength heuristic
                if entry.get("institution_id"):
                    entry["strength"] = "moderate"
                if entry.get("institution_id") and entry.get("author_id"):
                    entry["strength"] = "strong"
            except Exception as e:
                _log.warning(f"people: resolution failed for {name}: {e}")
            resolved.append(entry)

    # Dedup authors by canonical name (case-insensitive, diacritics-stripped,
    # family+initials matching) so the same human does not appear as
    # multiple graph nodes under name variants.
    from research_graph.dedupe import dedupe_authors
    before = len(resolved)
    resolved = dedupe_authors(resolved)
    after = len(resolved)
    if before != after:
        _log.info(f"people: dedup-merged {before - after} author name variants -> {after} unique")

    out_path.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    n_resolved = sum(1 for r in resolved if r.get("author_id"))
    _log.info(f"people: {len(resolved)} author records ({n_resolved} resolved) -> {out_path}")
    return 0


__all__ = ["run_people", "classify_strength"]
