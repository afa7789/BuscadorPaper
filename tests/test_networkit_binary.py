"""Tests for the compact NetworKit graph snapshot."""

from __future__ import annotations

import networkx as nx
import pytest

from research_graph.analysis.metrics import compute_networkit
from research_graph.graph.networkit_binary import (
    metadata_to_networkx,
    read_networkit_binary,
    write_networkit_binary,
)


def _graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("p0", node_type="paper", title="Paper zero")
    graph.add_node("p1", node_type="paper", title="Paper one")
    graph.add_node("a0", node_type="author", display_name="Author")
    graph.add_edge("p0", "p1", edge_type="CITES", confidence=0.8)
    graph.add_edge("p0", "p1", edge_type="EXTENDS", confidence=0.7)
    graph.add_edge("p1", "a0", edge_type="AUTHORED_BY", confidence=1.0)
    return graph


def test_binary_round_trip_preserves_metadata_and_multiplicity(tmp_path):
    source = _graph()
    topology_path, metadata_path = write_networkit_binary(source, tmp_path)

    assert topology_path.name == "graph.nkbg"
    assert metadata_path.name == "graph.nkbg.msgpack"
    topology, metadata = read_networkit_binary(topology_path)

    assert topology.numberOfNodes() == 3
    assert topology.numberOfEdges() == 2
    assert topology.weight(0, 1) == pytest.approx(2.0)
    assert len(metadata["edges"]) == 3

    restored = metadata_to_networkx(metadata)
    assert isinstance(restored, nx.MultiDiGraph)
    assert restored.number_of_edges("p0", "p1") == 2
    assert restored.nodes["p0"]["title"] == "Paper zero"


def test_networkit_metrics_use_binary_backend(tmp_path):
    topology_path, _ = write_networkit_binary(_graph(), tmp_path)
    topology, metadata = read_networkit_binary(topology_path)

    result = compute_networkit(topology, metadata)

    assert set(result["centrality"]) == {"p0", "p1"}
    assert result["centrality"]["p0"]["degree"] == pytest.approx(1.0)
    assert result["meta"] == {
        "node_count": 3,
        "edge_count": 3,
        "topology_edge_count": 2,
        "community_count": 1,
        "weak_component_count": 1,
        "backend": "networkit",
        "betweenness_mode": "exact",
    }


def test_reader_rejects_mismatched_sidecar(tmp_path):
    topology_path, metadata_path = write_networkit_binary(_graph(), tmp_path)
    payload = metadata_path.read_bytes()
    metadata_path.write_bytes(payload.replace(b"schema_version\x01", b"schema_version\x02"))

    with pytest.raises(ValueError, match="unsupported graph metadata schema"):
        read_networkit_binary(topology_path, metadata_path)
