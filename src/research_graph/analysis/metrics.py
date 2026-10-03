"""research_graph.analysis.metrics — centrality + communities + bridges."""

from __future__ import annotations

from collections import Counter

import community as community_louvain
import networkit as nk
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


def compute_networkit(graph: nk.Graph, metadata: dict) -> dict:
    """Compute graph metrics with NetworKit's compiled/parallel algorithms."""
    nodes = metadata.get("nodes", [])
    node_ids = [str(node["id"]) for node in nodes]
    paper_indices = [
        index
        for index, node in enumerate(nodes)
        if node.get("attrs", {}).get("node_type") == "paper"
    ]
    node_count = graph.numberOfNodes()

    degree_scores: list[float] = []
    denominator = max(1, node_count - 1)
    for node in range(node_count):
        if graph.isDirected():
            degree = graph.weightedDegree(node) + graph.weightedDegreeIn(node)
        else:
            degree = graph.weightedDegree(node)
        degree_scores.append(float(degree) / denominator)

    undirected = nk.graphtools.toUndirected(graph) if graph.isDirected() else graph
    shortest_path_graph = nk.graphtools.toUnweighted(undirected)
    if node_count == 0:
        betweenness_scores: list[float] = []
        pagerank_scores: list[float] = []
        betweenness_mode = "exact"
    else:
        if node_count <= 5_000:
            betweenness_scores = nk.centrality.Betweenness(
                shortest_path_graph,
                normalized=True,
                computeEdgeCentrality=False,
            ).run().scores()
            betweenness_mode = "exact"
        else:
            samples = min(1_024, max(64, int(node_count ** 0.5 * 8)))
            betweenness_scores = nk.centrality.EstimateBetweenness(
                shortest_path_graph,
                samples,
                normalized=True,
                parallel=True,
            ).run().scores()
            betweenness_mode = f"estimated:{samples}"
        pagerank_scores = nk.centrality.PageRank(
            graph,
            damp=0.85,
            tol=1e-8,
        ).run().scores()

    centrality = {
        node_ids[index]: {
            "degree": degree_scores[index],
            "betweenness": float(betweenness_scores[index]),
            "pagerank": float(pagerank_scores[index]),
        }
        for index in paper_indices
    }

    # Louvain runs only on paper-to-paper links, matching the NetworkX path.
    paper_position = {node: pos for pos, node in enumerate(paper_indices)}
    paper_graph = nk.Graph(len(paper_indices), weighted=True, directed=False)
    paper_edges: dict[tuple[int, int], float] = {}
    for source, target, weight in graph.iterEdgesWeights():
        if source not in paper_position or target not in paper_position or source == target:
            continue
        pair = tuple(sorted((paper_position[source], paper_position[target])))
        paper_edges[pair] = paper_edges.get(pair, 0.0) + float(weight)
    for (source, target), weight in paper_edges.items():
        paper_graph.addEdge(source, target, weight)

    communities: dict[str, int] = {}
    if paper_indices:
        if paper_graph.numberOfEdges() == 0:
            communities = {node_ids[index]: 0 for index in paper_indices}
        else:
            nk.setSeed(42, False)
            partition = nk.community.PLM(paper_graph, refine=True).run().getPartition()
            communities = {
                node_ids[node_index]: int(partition.subsetOf(position))
                for position, node_index in enumerate(paper_indices)
            }

    bridge_graph = nx.Graph()
    bridge_graph.add_nodes_from(range(len(paper_indices)))
    bridge_graph.add_edges_from(paper_edges)
    bridges = [
        (node_ids[paper_indices[source]], node_ids[paper_indices[target]])
        for source, target in nx.bridges(bridge_graph)
    ]

    if node_count == 0:
        weak_components = 0
    elif graph.isDirected():
        weak_components = (
            nk.components.WeaklyConnectedComponents(graph).run().numberOfComponents()
        )
    else:
        weak_components = nk.components.ConnectedComponents(graph).run().numberOfComponents()

    meta = {
        "node_count": int(node_count),
        "edge_count": len(metadata.get("edges", [])),
        "topology_edge_count": int(graph.numberOfEdges()),
        "community_count": len(set(communities.values())) if communities else 0,
        "weak_component_count": int(weak_components),
        "backend": "networkit",
        "betweenness_mode": betweenness_mode,
    }
    return {
        "centrality": centrality,
        "communities": communities,
        "bridges": bridges,
        "meta": meta,
    }
