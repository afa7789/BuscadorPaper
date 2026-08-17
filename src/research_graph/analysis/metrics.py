"""research_graph.analysis.metrics — centrality + communities + bridges."""

from __future__ import annotations

from collections import Counter

import community as community_louvain
import networkx as nx


def compute(graph: nx.MultiDiGraph) -> dict:
    """Return centrality, communities, bridges, and meta stats."""
    # Work on a paper-only undirected view for community detection
    paper_nodes = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "paper"]
    sub = graph.subgraph(paper_nodes).copy() if paper_nodes else nx.Graph()
    sub_undirected = sub.to_undirected() if sub.number_of_nodes() > 0 else sub

    # Centrality (on the full directed graph, paper nodes only)
    degree_c = nx.degree_centrality(graph)
    try:
        betweenness_c = nx.betweenness_centrality(graph.to_undirected(as_view=False))
    except Exception:
        betweenness_c = {n: 0.0 for n in graph.nodes()}
    try:
        pagerank_c = nx.pagerank(graph, alpha=0.85)
    except Exception:
        pagerank_c = {n: 0.0 for n in graph.nodes()}

    centrality: dict[str, dict[str, float]] = {}
    for nid in paper_nodes:
        centrality[nid] = {
            "degree": float(degree_c.get(nid, 0.0)),
            "betweenness": float(betweenness_c.get(nid, 0.0)),
            "pagerank": float(pagerank_c.get(nid, 0.0)),
        }

    # Communities (Louvain on undirected paper subgraph)
    communities: dict[str, int] = {}
    if sub_undirected.number_of_nodes() > 0:
        try:
            partition = community_louvain.best_partition(sub_undirected, random_state=42)
            for nid, cid in partition.items():
                communities[nid] = int(cid)
        except Exception:
            communities = {nid: 0 for nid in sub_undirected.nodes()}

    # Bridges (paper-to-paper only)
    bridges: list[tuple[str, str]] = []
    try:
        if sub_undirected.number_of_nodes() > 0:
            bridges = [(str(u), str(v)) for u, v in nx.bridges(sub_undirected)]
    except Exception:
        bridges = []

    # Meta
    weak_components = nx.number_weakly_connected_components(graph)
    meta = {
        "node_count": int(graph.number_of_nodes()),
        "edge_count": int(graph.number_of_edges()),
        "community_count": len(set(communities.values())) if communities else 0,
        "weak_component_count": int(weak_components),
    }
    return {
        "centrality": centrality,
        "communities": communities,
        "bridges": bridges,
        "meta": meta,
    }
