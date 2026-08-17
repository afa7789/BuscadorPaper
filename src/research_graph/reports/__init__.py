"""research_graph.reports — render the Markdown report from analysis + synthesis."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import networkx as nx

from research_graph.config import Config
from research_graph.logging_setup import configure_logging
from research_graph.models import ExtractionRecord, Paper
from research_graph.reports.markdown import render as render_markdown
from research_graph.reports.visualizations import embed_visualizations


_log = logging.getLogger(__name__)


def run_generate_report(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Compose the Markdown report from analysis + synthesis + papers + extractions + people."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load all artifacts
    papers = []
    if (out_dir / "papers.json").exists():
        papers = [Paper.model_validate(p) for p in json.loads((out_dir / "papers.json").read_text())]
    records = []
    if (out_dir / "extractions.json").exists():
        try:
            records = [ExtractionRecord.model_validate(r) for r in json.loads((out_dir / "extractions.json").read_text())]
        except Exception as e:
            _log.warning(f"generate-report: failed to parse extractions.json: {e}")
    analysis = {}
    if (out_dir / "analysis.json").exists():
        try:
            analysis = json.loads((out_dir / "analysis.json").read_text())
        except Exception as e:
            _log.warning(f"generate-report: failed to parse analysis.json: {e}")
    synthesis = {}
    if (out_dir / "synthesis.json").exists():
        try:
            synthesis = json.loads((out_dir / "synthesis.json").read_text())
        except Exception as e:
            _log.warning(f"generate-report: failed to parse synthesis.json: {e}")
    people = []
    if (out_dir / "people.json").exists():
        try:
            people = json.loads((out_dir / "people.json").read_text())
        except Exception as e:
            _log.warning(f"generate-report: failed to parse people.json: {e}")

    # Read graph (graphml)
    graph = nx.MultiDiGraph()
    graphml_path = out_dir / "graph.graphml"
    if graphml_path.exists():
        try:
            graph = nx.read_graphml(str(graphml_path))
        except Exception as e:
            _log.warning(f"generate-report: failed to read graph.graphml: {e}")

    body = render_markdown(
        config=config,
        graph=graph,
        analysis=analysis,
        synthesis=synthesis,
        papers=papers,
        records=records,
        people=people,
    )

    report_path = out_dir / "report.md"
    report_path.write_text(body, encoding="utf-8")
    embed_visualizations(report_path, out_dir / "graph.html", out_dir / "graph.mmd")
    _log.info(f"generate-report: {len(body)} chars -> {report_path}")
    return 0


__all__ = ["run_generate_report"]
