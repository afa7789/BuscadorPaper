"""research_graph.ingestion — public API and stage orchestrator.

Public API:
  - dispatch(entry, registry) -> list[Paper]
  - run_ingest(config, *, no_llm=False, continue_on_error=True) -> int

The orchestrator writes ``output_dir/papers.json`` (list of deduplicated Paper
records) and ``output_dir/ingest_summary.json`` with counts and timings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from research_graph.config import Config
from research_graph.ingestion.inputs import dispatch
from research_graph.ingestion.dedup import merge
from research_graph.providers import get_default_registry
from research_graph.logging_setup import configure_logging
from research_graph.providers._atomic import atomic_write_text


_log = logging.getLogger(__name__)


def run_ingest(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Run the ingest stage: resolve seed_inputs -> dedup -> write JSON."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        registry = get_default_registry(config)
    except Exception as e:
        _log.error(f"ingest: failed to build provider registry: {e}")
        if not continue_on_error:
            return 1
        registry = None

    all_papers = []
    for entry in config.seed_inputs:
        if registry is None:
            _log.warning(f"ingest: skipping {entry.type}={entry.value[:60]} (no registry)")
            continue
        papers = dispatch(entry, registry)
        _log.info(f"ingest: {entry.type}={entry.value[:60]} -> {len(papers)} papers")
        all_papers.extend(papers)

    merged = merge(all_papers)
    _log.info(f"ingest: {len(all_papers)} raw -> {len(merged)} after dedup")

    papers_path = out_dir / "papers.json"
    summary_path = out_dir / "ingest_summary.json"
    # Atomic writes via tmp + fsync + os.replace. Survives SIGKILL /
    # OOM / disk-full mid-write: papers.json either stays intact or
    # does not exist; the worst case is a stranded .tmp file alongside.
    atomic_write_text(
        papers_path,
        json.dumps([p.model_dump(mode="json") for p in merged], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    atomic_write_text(
        summary_path,
        json.dumps(
            {
                "schema_version": "1.0.0",
                "seed_count": len(config.seed_inputs),
                "raw_paper_count": len(all_papers),
                "merged_paper_count": len(merged),
                "providers": registry.names() if registry else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


__all__ = ["dispatch", "merge", "run_ingest"]
