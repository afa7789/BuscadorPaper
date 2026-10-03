"""research_graph.expansion.core — rank the graph so the core is its first N papers.

The graph may hold ``max_graph_papers``; only the first ``max_total_papers``
of this order go to the LLM and to PDF download. "Core" means: the user's
seeds, field research, and the papers most connected inside the graph.
"""

from __future__ import annotations

from collections import Counter

from research_graph.ingestion import _citations
from research_graph.ingestion.dedup import dedup_key
from research_graph.ingestion.methodology import classify
from research_graph.models import Paper


def canonical_links(raw: list[Paper], merged: list[Paper], links: list[dict]) -> list[dict]:
    """Rewrite link ends to the ids that survived dedup; drop links leaving the graph.

    A provider may name the same work ``doi:...`` and ``openalex:W...``; merge
    keeps the first id, so links are remapped through the shared dedup key.
    """
    final = {dedup_key(p): p.paper_id for p in merged}
    alias = {p.paper_id: final.get(dedup_key(p)) for p in raw}
    alias.update({p.paper_id: p.paper_id for p in merged})
    out: dict[tuple[str, str, str], dict] = {}
    for link in links:
        src, tgt = alias.get(link["src"]), alias.get(link["tgt"])
        if src and tgt and src != tgt:
            out.setdefault((src, tgt, link["type"]), {"src": src, "tgt": tgt, "type": link["type"]})
    return list(out.values())


def degree(links: list[dict]) -> dict[str, int]:
    """Number of in-corpus links touching each paper_id."""
    c: Counter[str] = Counter()
    for link in links:
        c[link["src"]] += 1
        c[link["tgt"]] += 1
    return dict(c)


def rank_core(papers: list[Paper], links: list[dict], seed_ids: set[str]) -> list[Paper]:
    """Best-first: seeds, primary research, graph degree, abstract, citations, year, id."""
    deg = degree(links)

    def key(p: Paper):
        return (
            0 if p.paper_id in seed_ids else 1,
            0 if classify(p) == "primary" else 1,
            -deg.get(p.paper_id, 0),
            0 if (p.abstract or "").strip() else 1,
            -_citations(p),
            -(p.year or 0),
            p.paper_id,
        )

    return sorted(papers, key=key)
