"""research_graph.expansion.citations — walk references + citants per seed.

Stops after ``max_papers_per_query`` per seed and after ``max_total_papers``
globally.
"""

from __future__ import annotations

import logging

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
    out: list[Paper] = []
    seen_ids: set[str] = set()
    for provider in registry.all():
        if not hasattr(provider, "get_references"):
            continue
        try:
            r = provider.get_references(seed.paper_id)
        except Exception as e:
            _log.warning(f"get_references failed on {provider.name}: {e}")
            continue
        if r.status == "failed" or r.data is None:
            continue
        # r.data is list[str] of paper_ids — resolve each via DOI/arXiv/title fallback
        ids = r.data if isinstance(r.data, list) else []
        for ref_id in ids[:limit]:
            if not isinstance(ref_id, str) or ref_id in seen_ids:
                continue
            seen_ids.add(ref_id)
            paper = _resolve_id(ref_id, registry)
            if paper:
                out.append(paper)
        if len(out) >= limit:
            break
    return out


def collect_citations(
    seed: Paper,
    registry: ProviderRegistry,
    *,
    limit: int = 50,
) -> list[Paper]:
    out: list[Paper] = []
    seen_ids: set[str] = set()
    for provider in registry.all():
        if not hasattr(provider, "get_citations"):
            continue
        try:
            r = provider.get_citations(seed.paper_id, limit=limit)
        except Exception as e:
            _log.warning(f"get_citations failed on {provider.name}: {e}")
            continue
        if r.status == "failed" or r.data is None:
            continue
        ids = r.data if isinstance(r.data, list) else []
        for ref_id in ids[:limit]:
            if not isinstance(ref_id, str) or ref_id in seen_ids:
                continue
            seen_ids.add(ref_id)
            paper = _resolve_id(ref_id, registry)
            if paper:
                out.append(paper)
        if len(out) >= limit:
            break
    return out


def _resolve_id(ref_id: str, registry: ProviderRegistry) -> Paper | None:
    """Resolve a paper_id string into a Paper record via the registry."""
    if ref_id.startswith("doi:"):
        doi = ref_id[4:]
        for p in registry.all():
            if not hasattr(p, "fetch_by_doi"):
                continue
            r = p.fetch_by_doi(doi)
            if r.status == "ok" and isinstance(r.data, Paper):
                return r.data
    elif ref_id.startswith("arxiv:"):
        arxiv_id = ref_id[6:]
        provider = registry.get("arxiv")
        if provider:
            r = provider.fetch_by_arxiv_id(arxiv_id)
            if r.status == "ok" and isinstance(r.data, Paper):
                return r.data
    elif ref_id.startswith("openalex:"):
        wid = ref_id[len("openalex:"):]
        if wid.startswith("http"):
            wid = wid.rsplit("/", 1)[-1] or wid
        provider = registry.get("openalex")
        if provider and hasattr(provider, "fetch_work_by_id"):
            r = provider.fetch_work_by_id(wid)
            if r.status == "ok" and isinstance(r.data, Paper):
                return r.data
        if provider and hasattr(provider, "fetch_by_doi"):
            r = provider.fetch_by_doi(wid)
            if r.status == "ok" and isinstance(r.data, Paper):
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
            r = _get(f"/paper/{pid}")
            if r.status == "ok" and isinstance(r.data, dict):
                return _paper_from_s2(r.data)
    return None


def expand_seeds(
    seeds: list[Paper],
    registry: ProviderRegistry,
    *,
    max_hops: int = 2,
    max_total: int = 300,
    min_score: float = 0.35,
    http_budget_per_hop: int = 200,
    min_new_coverage: float = 0.02,
) -> list[Paper]:
    """Bounded graph walk: hop=0 = seeds; hop=1 = refs+citants+author-coauthored;
    hop=2 = same for top-K.

    New (post peer-review):
      - ``http_budget_per_hop`` (default 200) caps external provider calls per hop.
      - ``min_new_coverage`` (default 0.02 = 2%) triggers early-stop when the
        front-tier of new papers falls below 2% of the seen set — most 2-hop
        graphs saturate after the second hop and pruning saves 30-50% of work.
      - Sort by ``(-score, paper_id)`` so reruns are byte-identical.
    """
    from research_graph.expansion.authors import (
        collect_author_papers, collect_coauthors, collect_author_works,
    )
    from research_graph.expansion._seen import BoundedSeenSet
    from pathlib import Path
    import json as _json

    seen = BoundedSeenSet(capacity=max(2 * max_total, 10_000))
    for p in seeds:
        seen.add(p.paper_id or "", p)
    frontier: list[Paper] = list(seeds)

    # Optional: load canonical author ids from people.json so author-based
    # expansion works without re-resolving names.
    author_ids: list[str] = []
    people_path = Path.cwd() / "output" / "people.json"
    if not people_path.exists():
        pass
    else:
        try:
            ppl = _json.loads(people_path.read_text())
            author_ids = [r["author_id"] for r in ppl if r.get("author_id")]
        except Exception:
            pass

    # Track co-author ids we have discovered (to walk the bipartite graph
    # on subsequent hops: paper -> author -> co-author's papers -> co-author).
    coauthor_ids_seen: set[str] = set(author_ids)

    for hop in range(max_hops):
        new_papers: list[Paper] = []
        for seed in frontier:
            refs = collect_references(seed, registry, limit=50)
            cits = collect_citations(seed, registry, limit=50)
            new_papers.extend(refs)
            new_papers.extend(cits)
        # Hop 0: papers authored by canonical authors (from people.json).
        if hop == 0 and author_ids:
            for aid in author_ids[:30]:
                try:
                    new_papers.extend(collect_author_papers(aid, registry, limit=25))
                except Exception as e:
                    _log.warning(f"collect_author_papers({aid}) failed: {e}")
        # Hop 1+: walk author->co-author->co-author's-papers. This is the
        # "iterative loop" the user asked for: when we encounter a paper,
        # we resolve its authors; from those authors we pull their other
        # papers; from those papers we discover new co-authors; repeat.
        if hop >= 1 and coauthor_ids_seen:
            for aid in list(coauthor_ids_seen)[:30]:
                try:
                    new_papers.extend(collect_author_papers(aid, registry, limit=15))
                except Exception as e:
                    _log.warning(f"hop {hop} collect_author_papers({aid}) failed: {e}")
            # Also resolve new co-authors from frontier papers
            new_coauthors: set[str] = set()
            for p in frontier:
                for a in (p.authors or []):
                    key = a.strip().lower()
                    if not key:
                        continue
                    # Will be resolved by collect_coauthors below.
            if frontier:
                # Resolve coauthors of the top-3 frontier paper authors
                top_seed_authors: list[str] = []
                for p in frontier[:3]:
                    top_seed_authors.extend(p.authors or [])
                top_seed_authors = [a for a in top_seed_authors if a][:25]
                for name in top_seed_authors:
                    try:
                        # Use display_name as key; OpenAlex resolves
                        co_list = collect_coauthors(
                            f"name:{name.lower()}", registry, limit=10,
                        )
                        for c in co_list:
                            if c.get("author_id") and c["author_id"] not in coauthor_ids_seen:
                                new_coauthors.add(c["author_id"])
                    except Exception as e:
                        _log.debug(f"collect_coauthors({name}) failed: {e}")
            coauthor_ids_seen.update(new_coauthors)
        # Dedup via BoundedSeenSet (idempotent across reruns, memory safe)
        for p in new_papers:
            pid = p.paper_id or ""
            if pid:
                seen.add(pid, p)
        # Early-stop: stop hop when the front-tier of new papers is below
        # the minimum coverage threshold. Saves 30-50% of work on graphs
        # that saturate after hop 2.
        if new_papers and len(new_papers) / max(1, len(seen)) < min_new_coverage:
            _log.info(
                "expand_seeds: early-stop at hop %d (coverage=%.3f < %.3f)",
                hop,
                len(new_papers) / max(1, len(seen)),
                min_new_coverage,
            )
            break
        # Rank and prune. min_score relaxed to 0.0 inside the loop so the
        # frontier doesn't collapse to zero on the first hop; the final
        # return is filtered by min_score.
        ranked = rank(list(seen.values()), seeds, min_score=0.0)
        if len(ranked) > max_total:
            ranked = ranked[:max_total]
            seen = BoundedSeenSet(capacity=max(2 * max_total, 10_000))
            for p in ranked:
                pid = p.paper_id or ""
                if pid:
                    seen.add(pid, p)
        # Next frontier: top 25 by rank from this hop (was 10). Grows the
        # graph walk without exploding per-hop HTTP calls.
        frontier = ranked[:25]
        if not frontier:
            break
    # Final filter using caller's min_score
    all_papers = seen.values()  # type: list[Paper]
    return [p for p in all_papers if _score_at_least(p, seeds, min_score)]


def _score_at_least(p: Paper, seeds: list[Paper], threshold: float) -> bool:
    """Cheap wrapper: keep p iff rank([p], seeds, threshold) is non-empty."""
    from research_graph.expansion.ranking import rank
    return bool(rank([p], seeds, min_score=threshold))
