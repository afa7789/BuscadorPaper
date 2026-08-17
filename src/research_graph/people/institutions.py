"""research_graph.people.institutions — aggregate author→institution edges.

Builds a concentration map and flags institutions with disproportionately
many in-scope authors (potential thematic hub).
"""

from __future__ import annotations

from research_graph.models import Institution, TypedEdge


def aggregate(
    edges: list[TypedEdge],
    institutions: list[Institution],
) -> dict:
    """Compute concentration + thematic hubs.

    Returns:
        {
          "institution_count": int,
          "author_count": int,
          "concentration": {institution_id: author_count},
          "hubs": [institution_id for inst_id with author_count >= median + std]
        }
    """
    from statistics import median, pstdev

    by_inst: dict[str, int] = {}
    for e in edges:
        if e.edge_type.value == "AFFILIATED_WITH":
            by_inst[e.target_node_id] = by_inst.get(e.target_node_id, 0) + 1

    if not by_inst:
        return {
            "institution_count": len(institutions),
            "author_count": 0,
            "concentration": {},
            "hubs": [],
        }

    counts = list(by_inst.values())
    med = median(counts)
    std = pstdev(counts) if len(counts) > 1 else 0.0
    threshold = med + std
    hubs = [iid for iid, c in by_inst.items() if c >= threshold and threshold > 0]
    return {
        "institution_count": len(institutions),
        "author_count": sum(counts),
        "concentration": by_inst,
        "hubs": hubs,
    }
