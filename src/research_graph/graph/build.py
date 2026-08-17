"""research_graph.graph.build — assemble typed heterogeneous graph.

Constructs a ``networkx.MultiDiGraph`` from papers, extraction records,
authors, institutions, methods, and open problems. Every node carries
``node_type``; every edge carries ``edge_type``, ``source``, ``confidence``,
and optional evidence text/location.
"""

from __future__ import annotations

from typing import Iterable

import networkx as nx

from research_graph.models import (
    Author,
    Concept,
    EdgeType,
    ExtractionRecord,
    Institution,
    Method,
    OpenProblem,
    Paper,
    TypedEdge,
)


def assemble(
    papers: list[Paper],
    records: list[ExtractionRecord] | None = None,
    authors: list[Author] | None = None,
    institutions: list[Institution] | None = None,
    methods: list[Method] | None = None,
    concepts: list[Concept] | None = None,
    open_problems: list[OpenProblem] | None = None,
) -> nx.MultiDiGraph:
    """Build the typed graph. Idempotent: composite edge dedup by (src, tgt, type)."""
    records = records or []
    authors = authors or []
    institutions = institutions or []
    methods = methods or []
    concepts = concepts or []
    open_problems = open_problems or []

    g: nx.MultiDiGraph = nx.MultiDiGraph()

    # ---- Nodes ---------------------------------------------------------------
    for p in papers:
        g.add_node(
            p.paper_id,
            node_type="paper",
            title=p.title,
            year=p.year,
            doi=p.doi,
            abstract=(p.abstract or "")[:500],
        )
    for a in authors:
        g.add_node(
            a.author_id,
            node_type="author",
            family=a.family,
            given=a.given,
            display_name=a.display_name,
        )
    for i in institutions:
        g.add_node(
            i.institution_id,
            node_type="institution",
            display_name=i.display_name,
            country=i.country,
            ror=i.ror,
        )
    for m in methods:
        g.add_node(m.method_key, node_type="method", label=m.label)
    for c in concepts:
        g.add_node(c.concept_id, node_type="concept", label=c.label, level=c.level)
    for op in open_problems:
        g.add_node(op.problem_hash, node_type="open_problem", statement=op.statement)

    # ---- Edges ---------------------------------------------------------------
    seen_edges: dict[tuple[str, str, str], dict] = {}

    def add_edge(src: str, tgt: str, et: EdgeType, **attrs) -> None:
        key = (src, tgt, et.value)
        existing = seen_edges.get(key)
        if existing is None:
            seen_edges[key] = attrs
            g.add_edge(src, tgt, edge_type=et, **attrs)
        else:
            # Keep highest confidence
            if attrs.get("confidence", 0) > existing.get("confidence", 0):
                existing.update(attrs)
                g[src][tgt][0].update(attrs)

    for p in papers:
        for a_name in p.authors:
            author_id = f"name:{a_name.lower()}"
            if not g.has_node(author_id):
                g.add_node(author_id, node_type="author", display_name=a_name)
            add_edge(
                p.paper_id, author_id, EdgeType.AUTHORED_BY,
                source="declared", confidence=1.0,
                evidence_text=a_name, evidence_location="paper.authors",
            )

    # ExtractionRecord-driven edges (paper -> method/concept/open_problem)
    rec_by_id: dict[str, ExtractionRecord] = {r.paper_id: r for r in records}
    for r in records:
        if not g.has_node(r.paper_id):
            continue
        for tech in r.proposed_technique:
            mid = f"method:{tech.lower().strip()}"
            if not g.has_node(mid):
                g.add_node(mid, node_type="method", label=tech)
            add_edge(
                r.paper_id, mid, EdgeType.USES_METHOD,
                source="llm", confidence=max(0.5, r.extraction_confidence),
                evidence_text=tech, evidence_location="extraction.proposed_technique",
            )
        for area in r.research_area:
            cid = f"concept:{area.lower().strip()}"
            if not g.has_node(cid):
                g.add_node(cid, node_type="concept", label=area)
            add_edge(
                r.paper_id, cid, EdgeType.SHARES_CONCEPT,
                source="llm", confidence=max(0.4, r.extraction_confidence),
                evidence_text=area, evidence_location="extraction.research_area",
            )
        for op in r.open_questions:
            add_edge(
                r.paper_id, op.problem_hash, EdgeType.LEAVES_OPEN,
                source="llm", confidence=op.confidence,
                evidence_text=op.statement, evidence_location="extraction.open_questions",
            )

    # Author -> Institution edges (synthesized from author list; v1: one
    # generic "affiliation" edge per author per paper; upgrade to ORCID-based
    # snapshot in v2).
    for inst in institutions:
        for a in authors:
            add_edge(
                a.author_id, inst.institution_id, EdgeType.AFFILIATED_WITH,
                source="openalex", confidence=0.6,
                evidence_text=None, evidence_location="people.professors",
            )

    return g
