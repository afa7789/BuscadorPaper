"""research_graph.expansion — bounded graph walk over references + citations + similarity + authors."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.config import Config
from research_graph.expansion.citations import expand_seeds
from research_graph.expansion.dedup_compat import merge_papers
from research_graph.logging_setup import configure_logging
from research_graph.models import Paper
from research_graph.providers import get_default_registry


_log = logging.getLogger(__name__)


def run_expand(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Run the expand stage: walks citation graph from each seed paper."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        _log.error("expand: papers.json not found; run `ingest` first")
        return 1
    try:
        seeds = [Paper.model_validate(p) for p in json.loads(papers_path.read_text())]
    except Exception as e:
        _log.error(f"expand: failed to read papers.json: {e}")
        return 1

    try:
        registry = get_default_registry(config)
    except Exception as e:
        _log.error(f"expand: failed to build registry: {e}")
        if not continue_on_error:
            return 1
        return 1

    try:
        expanded = expand_seeds(
            seeds,
            registry,
            max_hops=config.research_scope.max_hops,
            max_total=config.research_scope.max_total_papers,
            min_score=config.research_scope.min_relevance_score,
        )
        merged = merge_papers(seeds + expanded)
        papers_path.write_text(
            json.dumps([p.model_dump(mode="json") for p in merged], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _log.info(f"expand: {len(seeds)} seeds -> {len(merged)} after expansion")
        return 0
    except Exception as e:
        _log.error(f"expand failed: {e}")
        return 1 if not continue_on_error else 0


__all__ = ["expand_seeds", "run_expand"]
