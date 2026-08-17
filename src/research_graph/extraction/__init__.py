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

    records: list[ExtractionRecord] = []
    if no_llm:
        # Just declared records, no LLM
        for p in papers:
            rec = declared_to_extraction_record(p)
            rec.extraction_confidence = 0.0
            records.append(rec)
    else:
        try:
            llm = build_default_provider(config)
        except Exception as e:
            _log.warning(f"extract: could not build LLM provider ({e}); using declared records only")
            llm = None
        if llm is None:
            for p in papers:
                rec = declared_to_extraction_record(p)
                rec.extraction_confidence = 0.0
                records.append(rec)
        else:
            for p in papers:
                try:
                    rec = llm_extract(p, llm)
                    rec = classify(rec, llm)
                    records.append(rec)
                except Exception as e:
                    _log.warning(f"extract: failed for {p.paper_id}: {e}")
                    rec = declared_to_extraction_record(p)
                    rec.extraction_confidence = 0.0
                    records.append(rec)

    out_path = out_dir / "extractions.json"
    out_path.write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log.info(f"extract: {len(records)} records -> {out_path}")
    return 0


__all__ = ["run_extract", "extract"]
