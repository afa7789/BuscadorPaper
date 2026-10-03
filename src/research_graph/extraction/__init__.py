"""research_graph.extraction — extract structured records from Paper objects."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.config import Config
from research_graph.extraction.claims import classify
from research_graph.extraction.llm_extraction import extract as llm_extract
from research_graph.extraction.metadata import declared_to_extraction_record
from research_graph.llm import build_default_provider
from research_graph.logging_setup import configure_logging
from research_graph.models import ExtractionRecord, Paper


_log = logging.getLogger(__name__)


def run_extract(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Run extraction stage over papers.json -> extractions.json."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        _log.error("extract: papers.json not found; run `ingest` first")
        return 1

    try:
        papers = [Paper.model_validate(p) for p in json.loads(papers_path.read_text())]
    except Exception as e:
        _log.error(f"extract: failed to read papers.json: {e}")
        return 1

    llm = None if no_llm else _build_llm(config)
    # Only the core (papers.json is best-first after expand) goes to the LLM;
    # the rest of the graph keeps declared metadata.
    core_n = config.research_scope.max_total_papers if llm is not None else 0
    records: list[ExtractionRecord] = [
        _extract_one(p, llm) if i < core_n else _declared(p)
        for i, p in enumerate(papers)
    ]

    out_path = out_dir / "extractions.json"
    out_path.write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log.info(f"extract: {len(records)} records -> {out_path}")
    return 0


__all__ = ["run_extract", "extract"]


def _build_llm(config: Config):
    try:
        return build_default_provider(config)
    except Exception as e:
        _log.warning(f"extract: could not build LLM provider ({e}); using declared records only")
        return None


def _declared(p: Paper) -> ExtractionRecord:
    rec = declared_to_extraction_record(p)
    rec.extraction_confidence = 0.0
    return rec


def _extract_one(p: Paper, llm) -> ExtractionRecord:
    try:
        return classify(llm_extract(p, llm), llm)
    except Exception as e:
        _log.warning(f"extract: failed for {p.paper_id}: {e}")
        return _declared(p)
