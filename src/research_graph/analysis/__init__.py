"""research_graph.analysis — centrality + community + limitation grouping."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.analysis.metrics import compute as compute_metrics
from research_graph.config import Config
from research_graph.logging_setup import configure_logging


_log = logging.getLogger(__name__)


def run_analyze(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Compute graph metrics + bucket repeated limitations/future-work."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prefer graph.graphml because it round-trips node/edge attrs; fall back to
    # .gexf only if the user disabled graphml. If neither exists, fail.
    candidate_paths = []
    if (out_dir / "graph.graphml").exists():
        candidate_paths.append(out_dir / "graph.graphml")
    if (out_dir / "graph.gexf").exists():
        candidate_paths.append(out_dir / "graph.gexf")
    if not candidate_paths:
        _log.error(
            "analyze: no graph.graphml or graph.gexf found; run `build-graph` first "
            "(and consider setting outputs.save_graphml=true if both are off)"
        )
        return 1
    graph_path = candidate_paths[0]

    try:
        import networkx as nx
        graph = nx.read_graphml(str(graph_path))
    except Exception as e:
        _log.error(f"analyze: failed to read graph.graphml: {e}")
        return 1

    try:
        metrics = compute_metrics(graph)
    except Exception as e:
        _log.error(f"analyze: compute_metrics failed: {e}")
        if not continue_on_error:
            return 1
        metrics = {"centrality": {}, "communities": {}, "bridges": [], "meta": {"node_count": 0, "edge_count": 0, "community_count": 0, "weak_component_count": 0}}

    # Bucket repeated limitations / future-work from extractions.json (if present)
    extractions_path = out_dir / "extractions.json"
    buckets = {"limitations": {}, "future_work": {}}
    if extractions_path.exists():
        try:
            from research_graph.analysis.limitations import group as group_limits
            from research_graph.models import ExtractionRecord
            records = [ExtractionRecord.model_validate(r) for r in json.loads(extractions_path.read_text())]
            buckets = group_limits(records)
        except Exception as e:
            _log.warning(f"analyze: limitation grouping failed: {e}")

    metrics.update(buckets)

    out_path = out_dir / "analysis.json"
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    _log.info(f"analyze: {metrics.get('meta', {}).get('node_count', 0)} nodes, "
              f"{metrics.get('meta', {}).get('community_count', 0)} communities -> {out_path}")
    return 0


__all__ = ["run_analyze"]
