"""research_graph.graph.export — write the graph to GraphML, GEXF, Cytoscape JSON,
HTML (pyvis), and Mermaid.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import networkx as nx
from pyvis.network import Network


_SAFE_ID = re.compile(r"[^A-Za-z0-9_]")


def _sanitize(node_id: str) -> str:
    return _SAFE_ID.sub("_", node_id)


def _write_graphml(graph: nx.MultiDiGraph, output_dir: Path) -> str:
    # GraphML — strip non-serializable attrs first to avoid xml failures.
    # Enum values must be coerced to strings; nested containers are JSON-stringified.
    g_copy = graph.copy()
    for _, ndata in g_copy.nodes(data=True):
        _coerce_serializable(ndata)
    for _, _, edata in g_copy.edges(data=True):
        _coerce_serializable(edata)
    path = output_dir / "graph.graphml"
    nx.write_graphml(g_copy, str(path))
    return str(path)


def _coerce_serializable(data: dict) -> None:
    for k in list(data):
        v = data[k]
        if hasattr(v, "value"):  # Enum
            data[k] = v.value
        elif not isinstance(v, (str, int, float, bool)):
            data[k] = str(v)


def _write_gexf(graph: nx.MultiDiGraph, output_dir: Path) -> str:
    path = output_dir / "graph.gexf"
    nx.write_gexf(graph, str(path))
    return str(path)


def _write_cytoscape(graph: nx.MultiDiGraph, output_dir: Path) -> str:
    path = output_dir / "graph.cyjs"
    path.write_text(json.dumps(_to_cytoscape(graph), indent=2), encoding="utf-8")
    return str(path)


def _write_html(graph: nx.MultiDiGraph, output_dir: Path) -> str:
    # pyvis HTML — strip the "source" attribute (collides with add_edge(source, target))
    g_for_pyvis = graph.copy()
    for _, _, edata in g_for_pyvis.edges(data=True):
        edata.pop("source", None)
    path = output_dir / "graph.html"
    net = Network(height="800px", width="100%", directed=True, notebook=False,
                  cdn_resources="in_line")
    net.from_nx(g_for_pyvis)
    # Bound physics stabilization so the page renders in a few seconds instead
    # of sitting on a frozen progress bar for 15s+ with 1000+ nodes.
    net.set_options(
        '{"layout": {"improvedLayout": false}, "physics": {"solver": "forceAtlas2Based", '
        '"stabilization": {"iterations": 100, "updateInterval": 100}}}'
    )
    net.save_graph(str(path))
    return str(path)


def _write_mermaid(graph: nx.MultiDiGraph, output_dir: Path) -> str:
    path = output_dir / "graph.mmd"
    path.write_text(to_mermaid(graph), encoding="utf-8")
    return str(path)


def export_all(
    graph: nx.MultiDiGraph,
    output_dir: str | Path,
    *,
    save_graphml: bool = False,
    save_gexf: bool = False,
    save_html_graph: bool = True,
    save_mermaid: bool = False,
    save_cytoscape_json: bool = False,
) -> dict[str, str]:
    """Export the graph in requested formats only.

    By default produces ``graph.html`` (pyvis). Other formats are off until
    you ask: saves time, disk space, and reduces ``output/`` clutter.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    writers = [
        (save_graphml, "graphml", _write_graphml),
        (save_gexf, "gexf", _write_gexf),
        (save_cytoscape_json, "cyjs", _write_cytoscape),
        (save_html_graph, "html", _write_html),
        (save_mermaid, "mermaid", _write_mermaid),
    ]
    paths: dict[str, str] = {}
    for enabled, key, writer in writers:
        if enabled:
            paths[key] = writer(graph, output_dir)
    return paths


def _to_cytoscape(graph: nx.MultiDiGraph) -> dict[str, list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    for nid, data in graph.nodes(data=True):
        nodes.append({
            "data": {"id": str(nid), "label": str(data.get("title") or data.get("label") or data.get("display_name") or nid),
                      "node_type": data.get("node_type", "")},
        })
    edges: list[dict[str, Any]] = []
    eid = 0
    for src, tgt, data in graph.edges(data=True):
        edges.append({
            "data": {
                "id": f"e{eid}",
                "source": str(src),
                "target": str(tgt),
                "edge_type": data.get("edge_type", ""),
                "confidence": data.get("confidence", 0.0),
            }
        })
        eid += 1
    return {"nodes": nodes, "edges": edges}


def to_mermaid(graph: nx.MultiDiGraph, max_nodes: int = 80) -> str:
    """Emit a Mermaid `graph LR` block, truncated to the highest-degree nodes."""
    if graph.number_of_nodes() == 0:
        return "graph LR\n  empty[No nodes]"

    # Select top-N by degree
    deg = dict(graph.degree())
    top_ids = sorted(deg, key=lambda n: deg[n], reverse=True)[:max_nodes]
    sub = graph.subgraph(top_ids)

    lines: list[str] = ["graph LR"]
    for nid in sub.nodes():
        data = sub.nodes[nid]
        label = (
            data.get("title")
            or data.get("label")
            or data.get("display_name")
            or str(nid)
        )
        label = label.replace('"', "'")[:60]
        lines.append(f'  {_sanitize(str(nid))}["{data.get("node_type","node")}: {label}"]')
    for src, tgt, data in sub.edges(data=True):
        et = data.get("edge_type", "")
        lines.append(f'  {_sanitize(str(src))} -->|{et}| {_sanitize(str(tgt))}')
    return "\n".join(lines)
