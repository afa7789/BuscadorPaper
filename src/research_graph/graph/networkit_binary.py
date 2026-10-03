"""Compact NetworKit topology plus a lossless MessagePack metadata sidecar.

``NetworkitBinaryGraph`` is intentionally topology-oriented: it stores numeric
node ids and weighted edges very efficiently, but not arbitrary Python
attributes or parallel-edge payloads.  The adjacent MessagePack file keeps the
stable external ids, node attributes, and every original typed edge.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import msgpack
import networkit as nk
import networkx as nx


TOPOLOGY_FILENAME = "graph.nkbg"
METADATA_FILENAME = "graph.nkbg.msgpack"
SCHEMA_VERSION = 1


def _primitive(value: Any) -> Any:
    """Convert graph values to types that MessagePack can encode exactly."""
    if isinstance(value, Enum):
        return _primitive(value.value)
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_primitive(item) for item in value]
    return str(value)


def write_networkit_binary(
    graph: nx.Graph,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write a fast topology snapshot and its lossless metadata sidecar.

    Parallel NetworkX edges are collapsed into one weighted topology edge. The
    weight is their multiplicity, which preserves degree and PageRank mass.
    Every individual edge remains available in the MessagePack sidecar.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    topology_path = output_dir / TOPOLOGY_FILENAME
    metadata_path = output_dir / METADATA_FILENAME
    topology_tmp = output_dir / f"{TOPOLOGY_FILENAME}.tmp"
    metadata_tmp = output_dir / f"{METADATA_FILENAME}.tmp"

    node_ids = list(graph.nodes())
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    topology = nk.Graph(
        len(node_ids),
        weighted=True,
        directed=graph.is_directed(),
    )

    collapsed: dict[tuple[int, int], float] = {}
    if graph.is_multigraph():
        original_edges = list(graph.edges(keys=True, data=True))
        for source, target, _key, _attrs in original_edges:
            pair = (node_index[source], node_index[target])
            if not graph.is_directed() and pair[1] < pair[0]:
                pair = (pair[1], pair[0])
            collapsed[pair] = collapsed.get(pair, 0.0) + 1.0
    else:
        original_edges = [
            (source, target, 0, attrs)
            for source, target, attrs in graph.edges(data=True)
        ]
        for source, target, _key, _attrs in original_edges:
            pair = (node_index[source], node_index[target])
            if not graph.is_directed() and pair[1] < pair[0]:
                pair = (pair[1], pair[0])
            collapsed[pair] = collapsed.get(pair, 0.0) + 1.0

    for (source, target), weight in sorted(collapsed.items()):
        topology.addEdge(source, target, weight)

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "directed": graph.is_directed(),
        "multigraph": graph.is_multigraph(),
        "nodes": [
            {
                "id": str(node_id),
                "attrs": _primitive(dict(graph.nodes[node_id])),
            }
            for node_id in node_ids
        ],
        "edges": [
            {
                "source": node_index[source],
                "target": node_index[target],
                "key": _primitive(key),
                "attrs": _primitive(dict(attrs)),
            }
            for source, target, key, attrs in original_edges
        ],
    }

    try:
        nk.graphio.NetworkitBinaryWriter().write(topology, str(topology_tmp))
        metadata_tmp.write_bytes(msgpack.packb(metadata, use_bin_type=True))
        os.replace(topology_tmp, topology_path)
        os.replace(metadata_tmp, metadata_path)
    finally:
        topology_tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)

    return topology_path, metadata_path


def read_networkit_binary(
    topology_path: str | Path,
    metadata_path: str | Path | None = None,
) -> tuple[nk.Graph, dict[str, Any]]:
    """Read a topology snapshot and validate its MessagePack sidecar."""
    topology_path = Path(topology_path)
    if metadata_path is None:
        metadata_path = topology_path.with_name(METADATA_FILENAME)
    metadata_path = Path(metadata_path)

    topology = nk.graphio.NetworkitBinaryReader().read(str(topology_path))
    metadata = msgpack.unpackb(metadata_path.read_bytes(), raw=False)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported graph metadata schema: {metadata.get('schema_version')!r}"
        )
    if len(metadata.get("nodes", [])) != topology.numberOfNodes():
        raise ValueError("graph topology and metadata node counts do not match")
    return topology, metadata


def metadata_to_networkx(metadata: dict[str, Any]) -> nx.Graph:
    """Reconstruct the lossless NetworkX graph from the metadata sidecar."""
    directed = bool(metadata.get("directed", True))
    multigraph = bool(metadata.get("multigraph", True))
    if directed and multigraph:
        graph: nx.Graph = nx.MultiDiGraph()
    elif directed:
        graph = nx.DiGraph()
    elif multigraph:
        graph = nx.MultiGraph()
    else:
        graph = nx.Graph()

    nodes = metadata.get("nodes", [])
    for node in nodes:
        graph.add_node(node["id"], **node.get("attrs", {}))
    for edge in metadata.get("edges", []):
        source = nodes[edge["source"]]["id"]
        target = nodes[edge["target"]]["id"]
        attrs = edge.get("attrs", {})
        if multigraph:
            graph.add_edge(source, target, key=edge.get("key"), **attrs)
        else:
            graph.add_edge(source, target, **attrs)
    return graph
