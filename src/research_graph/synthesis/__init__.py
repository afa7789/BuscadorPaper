"""research_graph.synthesis — LLM-driven synthesis stage."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.config import Config
from research_graph.llm import build_default_provider
from research_graph.logging_setup import configure_logging
from research_graph.models import ExtractionRecord, Paper
from research_graph.synthesis.communities import narrate
from research_graph.synthesis.executive import summary as exec_summary
from research_graph.synthesis.limitations_split import render as render_lim_split
from research_graph.synthesis.project_ideas import propose


_log = logging.getLogger(__name__)


def run_synthesize(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Build the synthesis dict (executive + communities + ideas + declared-vs-inferred)."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    extractions_path = out_dir / "extractions.json"
    analysis_path = out_dir / "analysis.json"
    if not papers_path.exists():
        _log.error("synthesis: papers.json not found")
        return 1

    papers = [Paper.model_validate(p) for p in json.loads(papers_path.read_text())]
    records = []
    if extractions_path.exists():
        records = [ExtractionRecord.model_validate(r) for r in json.loads(extractions_path.read_text())]
    analysis = {}
    if analysis_path.exists():
        try:
            analysis = json.loads(analysis_path.read_text())
        except Exception:
            analysis = {}

    synth: dict = {
        "executive_summary": "",
        "how_seeds_connect": "",
        "per_community_narrative": {},
        "declared_vs_inferred": {"declared": [], "inferred": []},
        "project_ideas": [],
    }

    # Declared-vs-inferred can run without LLM (purely structural)
    try:
        synth["declared_vs_inferred"] = render_lim_split(records, llm=None)
    except Exception as e:
        _log.warning(f"synthesis: declared_vs_inferred failed: {e}")

    if no_llm:
        synth["executive_summary"] = "(LLM disabled — no executive summary)"
        out_path = out_dir / "synthesis.json"
        out_path.write_text(json.dumps(synth, indent=2, ensure_ascii=False), encoding="utf-8")
        _log.info(f"synthesis: no-llm -> {out_path}")
        return 0

    try:
        llm = build_default_provider(config)
    except Exception as e:
        _log.warning(f"synthesis: could not build LLM provider ({e})")
        llm = None

    if llm is not None:
        try:
            synth["executive_summary"] = exec_summary(analysis, papers, llm)
        except Exception as e:
            _log.warning(f"synthesis: executive_summary failed: {e}")
        try:
            synth["per_community_narrative"] = narrate(analysis, papers, llm)
        except Exception as e:
            _log.warning(f"synthesis: communities failed: {e}")
        try:
            synth["project_ideas"] = [
                idea.model_dump(mode="json")
                for idea in propose(analysis, papers, records, llm,
                                    n=8, min_supporting=2)
            ]
        except Exception as e:
            _log.warning(f"synthesis: project_ideas failed: {e}")

    out_path = out_dir / "synthesis.json"
    out_path.write_text(json.dumps(synth, indent=2, ensure_ascii=False), encoding="utf-8")
    _log.info(f"synthesis: {len(synth['project_ideas'])} ideas -> {out_path}")
    return 0


__all__ = ["run_synthesize"]
