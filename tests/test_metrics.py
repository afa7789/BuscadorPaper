"""Tests for analysis.metrics.compute."""

import networkx as nx

from research_graph.analysis.metrics import compute


def test_compute_empty_graph():
    g = nx.MultiDiGraph()
    out = compute(g)
    assert out["centrality"] == {}
    assert out["communities"] == {}


def test_compute_small_graph():
    g = nx.MultiDiGraph()
    for i in range(5):
        g.add_node(f"p{i}", node_type="paper", title=f"P{i}")
    g.add_edge("p0", "p1", edge_type="CITES", confidence=1.0, source="x")
    g.add_edge("p1", "p2", edge_type="CITES", confidence=1.0, source="x")
    g.add_edge("p2", "p3", edge_type="CITES", confidence=1.0, source="x")
    out = compute(g)
    assert "p0" in out["centrality"]
    assert "centrality" in out
    assert "communities" in out
    assert "bridges" in out
    assert out["meta"]["node_count"] == 5
    # 4-node chain (p0->p1->p2->p3) has 3 edges
    assert out["meta"]["edge_count"] == 3
