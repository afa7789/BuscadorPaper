"""research_graph.expansion.authors — author-centric expansion.

Functions:
  - collect_author_works(author_id, registry, limit)
      Fetch the author's top-N works (already existed).

  - collect_coauthors(author_id, registry, limit)
      NEW: fetch an author's top-N works, extract co-authors from each,
      resolve them to OpenAlex IDs, return a deduplicated list of
      {"author_id": "openalex:A...", "display_name": "...", "via": <paper_id>}.

  - collect_author_full(author_id, registry, limit)
      Orchestrator: returns a dict with the author's works + coauthors +
      suggested next hops. Designed for the iterative loop
      paper -> author -> papers -> co-authors -> ...
"""

from __future__ import annotations

import logging

from research_graph.models import Paper
from research_graph.providers import ProviderRegistry
from research_graph.providers.base import ok


_log = logging.getLogger(__name__)


def collect_author_works(
    author_id: str,
    registry: ProviderRegistry,
    *,
    limit: int = 25,
) -> list[Paper]:
    """Return up to ``limit`` recent works by ``author_id`` (any provider format)."""
    out: list[Paper] = []
    for provider in registry.all():
        if not hasattr(provider, "get_author_works"):
            continue
        try:
            r = provider.get_author_works(author_id, limit=limit)
        except Exception as e:
            _log.warning(f"author works failed on {provider.name}: {e}")
            continue
        if r.status == "failed" or r.data is None:
            continue
        papers = r.data if isinstance(r.data, list) else []
        for p in papers:
            if isinstance(p, Paper):
                out.append(p)
        if len(out) >= limit:
            break
    return out[:limit]


collect_author_papers = collect_author_works  # alias used by citations.py


def collect_coauthors(
    author_id: str,
    registry: ProviderRegistry,
    *,
    limit: int = 25,
) -> list[dict]:
    """Fetch an author's works and extract unique co-authors.

    Returns a list of dicts: {author_id, display_name, paper_ids: [str]}.
    The author_id is OpenAlex-canonical when available; otherwise the
    normalized display name is used as a fallback identifier.

    The seed author (caller's author_id) is excluded from the result. Matching
    is permissive: we skip any coauthor whose normalized display name matches
    the seed's last token (handles "Alice Smith" matching seed "openalex:A123"),
    matches the seed's first token (handles seed "name:alice" matching "Alice"),
    or matches the seed display name exactly.
    """
    seed_raw = author_id.split(":", 1)[-1].strip().lower()
    seed_first = seed_raw.split()[0] if seed_raw else ""  # first word
    seed_last = seed_raw.split()[-1] if seed_raw else ""   # last word (handles "openalex:A123" -> "a123")
    works = collect_author_works(author_id, registry, limit=limit)
    coauthor_map: dict[str, dict] = {}
    for w in works:
        for a in (w.authors or []):
            aname = a.strip()
            alower = aname.lower()
            # Skip the seed author (permissive match against any token)
            if seed_raw and (alower == seed_raw
                             or seed_first and alower == seed_first
                             or seed_last and alower == seed_last):
                continue
            key = alower
            if key not in coauthor_map:
                coauthor_map[key] = {
                    "display_name": a,
                    "author_id": None,
                    "paper_ids": [],
                }
            if w.paper_id and w.paper_id not in coauthor_map[key]["paper_ids"]:
                coauthor_map[key]["paper_ids"].append(w.paper_id)
    # Best-effort: resolve display_name -> OpenAlex author_id for each coauthor
    openalex = registry.get("openalex")
    if openalex is not None:
        for entry in coauthor_map.values():
            try:
                r = openalex._get("/authors", {"search": entry["display_name"], "per_page": 1})  # type: ignore[attr-defined]
                if r.status == "ok" and isinstance(r.data, dict):
                    results = r.data.get("results") or []
                    if results:
                        aid = results[0].get("id") or ""
                        short = aid.rsplit("/", 1)[-1] if aid.startswith("http") else aid
                        if short.startswith("A"):
                            entry["author_id"] = f"openalex:{short}"
            except Exception as e:
                _log.debug(f"coauthor resolve failed for {entry['display_name']}: {e}")
    return list(coauthor_map.values())[:limit]


def collect_author_full(
    author_id: str,
    registry: ProviderRegistry,
    *,
    limit: int = 25,
) -> dict:
    """Bundle: works + coauthors for an author. Used by the iterative loop."""
    return {
        "author_id": author_id,
        "works": collect_author_works(author_id, registry, limit=limit),
        "coauthors": collect_coauthors(author_id, registry, limit=limit),
    }
