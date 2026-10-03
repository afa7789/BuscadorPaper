"""research_graph.expansion.citations — walk references + citants per seed.

Each run walks at most ``max_hops`` hops from the frontier; ``ExpandState``
remembers the frontier so the next run continues where this one stopped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from research_graph.expansion.ranking import rank
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


_log = logging.getLogger(__name__)


def collect_references(
    seed: Paper,
    registry: ProviderRegistry,
    *,
    limit: int = 50,
) -> list[Paper]:
    return _collect(seed, registry, "get_references", limit=limit)


def collect_citations(
    seed: Paper,
    registry: ProviderRegistry,
    *,
    limit: int = 50,
) -> list[Paper]:
    return _collect(seed, registry, "get_citations", limit=limit)


def _call(provider, method: str, seed: Paper, limit: int):
    if method == "get_citations":
        return provider.get_citations(seed.paper_id, limit=limit)
    return provider.get_references(seed.paper_id)


def _collect(seed: Paper, registry: ProviderRegistry, method: str, *, limit: int) -> list[Paper]:
    """Walk providers in priority order until ``limit`` papers are collected.

    Providers may return Paper objects (OpenAlex: no extra request) or id
    strings, which are resolved one by one via ``_resolve_id``.
    """
    out: list[Paper] = []
    seen_ids: set[str] = set()
    for provider in registry.all():
        if not hasattr(provider, method):
            continue
        try:
            r = _call(provider, method, seed, limit)
        except Exception as e:
            _log.warning(f"{method} failed on {provider.name}: {e}")
            continue
        if r is None or r.status == "failed" or not isinstance(r.data, list):
            continue
        for item in r.data[:limit]:
            paper = _to_paper(item, seen_ids, registry)
            if paper:
                out.append(paper)
        if len(out) >= limit:
            break
    return out


def _to_paper(item, seen_ids: set[str], registry: ProviderRegistry) -> Paper | None:
    key = item.paper_id if isinstance(item, Paper) else item
    if not isinstance(key, str) or key in seen_ids:
        return None
    seen_ids.add(key)
    return item if isinstance(item, Paper) else _resolve_id(key, registry)


def _resolve_id(ref_id: str, registry: ProviderRegistry) -> Paper | None:
    """Resolve a paper_id string into a Paper record via the registry."""
    try:
        if ref_id.startswith("doi:"):
            doi = ref_id[4:]
            for p in registry.all():
                if not hasattr(p, "fetch_by_doi"):
                    continue
                try:
                    r = p.fetch_by_doi(doi)
                except Exception as e:
                    _log.warning(f"fetch_by_doi({doi}) failed on {p.name}: {e}")
                    continue
                if r is not None and r.status == "ok" and isinstance(r.data, Paper):
                    return r.data
        elif ref_id.startswith("arxiv:"):
            arxiv_id = ref_id[6:]
            provider = registry.get("arxiv")
            if provider:
                try:
                    r = provider.fetch_by_arxiv_id(arxiv_id)
                except Exception as e:
                    _log.warning(f"fetch_by_arxiv_id({arxiv_id}) failed: {e}")
                    r = None
                if r is not None and r.status == "ok" and isinstance(r.data, Paper):
                    return r.data
        elif ref_id.startswith("openalex:"):
            wid = ref_id[len("openalex:"):]
            if wid.startswith("http"):
                wid = wid.rsplit("/", 1)[-1] or wid
            provider = registry.get("openalex")
            if provider and hasattr(provider, "fetch_work_by_id"):
                try:
                    r = provider.fetch_work_by_id(wid)
                except Exception as e:
                    _log.warning(f"fetch_work_by_id({wid}) failed: {e}")
                    r = None
                if r is not None and r.status == "ok" and isinstance(r.data, Paper):
                    return r.data
            if provider and hasattr(provider, "fetch_by_doi"):
                try:
                    r = provider.fetch_by_doi(wid)
                except Exception as e:
                    _log.warning(f"fetch_by_doi({wid}) failed: {e}")
                    r = None
                if r is not None and r.status == "ok" and isinstance(r.data, Paper):
                    return r.data
        elif ref_id.startswith("s2:") or (len(ref_id) == 40 and ref_id.isalnum()):
            # Semantic Scholar paper id (40-char hex) or explicit "s2:" prefix
            pid = ref_id[3:] if ref_id.startswith("s2:") else ref_id
            from research_graph.providers.semantic_scholar import _paper_from_s2
            for p in registry.all():
                if p.name != "semantic_scholar":
                    continue
                _get = getattr(p, "_get", None)
                if _get is None:
                    continue
                try:
                    r = _get(f"/paper/{pid}")
                except Exception as e:
                    _log.warning(f"s2 lookup {pid} failed: {e}")
                    continue
                if r is not None and r.status == "ok" and isinstance(r.data, dict):
                    return _paper_from_s2(r.data)
    except Exception as e:
        _log.warning(f"_resolve_id({ref_id}) failed: {e}")
    return None


_FRONTIER_SIZE = 25


@dataclass
class ExpandState:
    """What expand already did, persisted between runs (output/expand_state.json)."""

    frontier: list[str] = field(default_factory=list)
    walked: set[str] = field(default_factory=set)
    authors_done: set[str] = field(default_factory=set)
    hops_done: int = 0

    def to_json(self) -> dict:
        return {"frontier": self.frontier, "walked": sorted(self.walked),
                "authors_done": sorted(self.authors_done), "hops_done": self.hops_done}

    @classmethod
    def from_json(cls, d: dict) -> "ExpandState":
        return cls(frontier=list(d.get("frontier") or []), walked=set(d.get("walked") or []),
                   authors_done=set(d.get("authors_done") or []),
                   hops_done=int(d.get("hops_done") or 0))


def expand_seeds(
    seeds: list[Paper],
    registry: ProviderRegistry,
    *,
    max_hops: int = 2,
    max_total: int | None = None,
    min_score: float = 0.35,
    min_new_coverage: float = 0.02,
    expand_by: list[str] | None = None,
    links: list[dict] | None = None,
    state: ExpandState | None = None,
) -> list[Paper]:
    """Walk up to ``max_hops`` hops from the frontier; return seeds + papers found.

      - Hop budget, not graph size, bounds a run: each hop walks the top-25
        not-yet-walked papers. ``max_total`` (None = no cap) optionally caps the graph.
      - ``state`` (optional, mutated): resume point. Empty state -> start from
        ``seeds``; otherwise continue from ``state.frontier`` and never re-walk
        a paper or an author.
      - ``min_new_coverage`` (default 2%) early-stops when a hop adds little.
      - ``expand_by`` picks the axes: "references", "citations", "authors".
      - ``links`` (optional out-param) receives one ``{src, tgt, type: "cites"}``
        per citation edge walked.
      - Author axis: first hop of a fresh run walks people.json authors; later
        hops walk the OpenAlex author ids carried by frontier papers.
    """
    from research_graph.expansion._seen import BoundedSeenSet

    state = state if state is not None else ExpandState()
    axes = set(expand_by) if expand_by is not None else {"references", "citations", "authors"}
    walkers = [(axis, w) for axis, w in (("references", collect_references),
                                         ("citations", collect_citations)) if axis in axes]
    edges = links if links is not None else []
    topic = _topic_seeds(seeds)
    fresh = state.hops_done == 0
    capacity = max(2 * max_total, 10_000) if max_total else 1_000_000

    seen = BoundedSeenSet(capacity=capacity)
    for p in seeds:
        seen.add(p.paper_id or "", p)
    frontier = _start_frontier(seeds, state)

    for hop in range(max_hops):
        if not frontier:
            break
        state.walked.update(p.paper_id for p in frontier)
        state.hops_done += 1
        new_papers = _walk_citations(frontier, walkers, registry, edges)
        if "authors" in axes:
            ids = _people_author_ids() if fresh and hop == 0 else _frontier_author_ids(frontier)
            new_papers += _walk_authors(ids, state.authors_done, registry,
                                        limit=25 if fresh and hop == 0 else 15)
        for p in new_papers:
            if p.paper_id:
                seen.add(p.paper_id, p)
        ranked = rank(list(seen.values()), topic, min_score=0.0)[:max_total]
        seen = BoundedSeenSet(capacity=capacity)
        for p in ranked:
            seen.add(p.paper_id or "", p)
        frontier = [p for p in ranked if p.paper_id not in state.walked][:_FRONTIER_SIZE]
        coverage = len(new_papers) / max(1, len(seen))
        if new_papers and coverage < min_new_coverage:
            _log.info("expand_seeds: early-stop at hop %d (coverage=%.3f < %.3f)",
                      hop, coverage, min_new_coverage)
            break
    state.frontier = [p.paper_id for p in frontier]
    return [p for p in seen.values() if _score_at_least(p, topic, min_score)]


def _topic_seeds(papers: list[Paper]) -> list[Paper]:
    """Relevance anchors: the papers ingest produced (not everything expand added)."""
    marked = [p for p in papers
              if (p.source_provenance or {}).get("ingest_seed")
              or (p.source_provenance or {}).get("explicit_seed")]
    return marked or papers


def _start_frontier(seeds: list[Paper], state: ExpandState) -> list[Paper]:
    if state.hops_done == 0:
        return [p for p in seeds if p.paper_id not in state.walked]
    by_id = {p.paper_id: p for p in seeds}
    return [by_id[i] for i in state.frontier if i in by_id and i not in state.walked]


def _walk_citations(frontier, walkers, registry, edges: list[dict]) -> list[Paper]:
    """Refs and citants of every frontier paper; appends one edge per paper found."""
    found: list[Paper] = []
    for paper in frontier:
        for axis, walk in walkers:
            for other in walk(paper, registry, limit=50):
                src, tgt = (paper, other) if axis == "references" else (other, paper)
                edges.append({"src": src.paper_id, "tgt": tgt.paper_id, "type": "cites"})
                found.append(other)
    return found


def _walk_authors(author_ids, done: set[str], registry, *, limit: int) -> list[Paper]:
    """Works of up to 30 not-yet-walked authors."""
    from research_graph.expansion.authors import collect_author_papers

    found: list[Paper] = []
    for aid in [a for a in dict.fromkeys(author_ids) if a not in done][:30]:
        done.add(aid)
        try:
            found.extend(collect_author_papers(aid, registry, limit=limit))
        except Exception as e:
            _log.warning(f"collect_author_papers({aid}) failed: {e}")
    return found


def _frontier_author_ids(frontier: list[Paper]) -> list[str]:
    ids: list[str] = []
    for p in frontier:
        raw = (p.source_provenance or {}).get("openalex_author_ids") or []
        ids.extend(raw if isinstance(raw, list) else [raw])
    return ids


def _people_author_ids() -> list[str]:
    """Canonical author ids from output/people.json (written by the people stage)."""
    import json as _json
    from pathlib import Path

    people_path = Path.cwd() / "output" / "people.json"
    if not people_path.exists():
        return []
    try:
        return [r["author_id"] for r in _json.loads(people_path.read_text()) if r.get("author_id")]
    except Exception:
        return []


def _score_at_least(p: Paper, seeds: list[Paper], threshold: float) -> bool:
    """Cheap wrapper: keep p iff rank([p], seeds, threshold) is non-empty."""
    from research_graph.expansion.ranking import rank
    return bool(rank([p], seeds, min_score=threshold))
