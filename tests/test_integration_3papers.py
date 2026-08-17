"""End-to-end smoke test using the 3 PDFs the user provided in the repo.

Skips cleanly if the PDFs are absent. Never fabricates scientific results:
any provider failure simply leaves the corresponding papers absent.
"""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
PDFS = [
    REPO_ROOT / "3795774.pdf",
    REPO_ROOT / "3805044.pdf",
    REPO_ROOT / "Proposta_Mestrado-2.pdf",
]


@pytest.mark.skipif(not all(p.exists() for p in PDFS), reason="seed PDFs not present")
def test_pipeline_runs_on_three_pdfs(tmp_path):
    """End-to-end: ingest -> extract (no-llm) -> build-graph -> analyze -> report."""
    from research_graph.config import Config
    from research_graph.ingestion import run_ingest
    from research_graph.extraction import run_extract
    from research_graph.graph import run_build_graph
    from research_graph.analysis import run_analyze
    from research_graph.reports import run_generate_report

    # Build a config that points at the 3 PDFs
    cfg = Config.model_validate({
        "project": {
            "name": "test-3papers",
            "language": "pt-BR",
            "output_dir": str(tmp_path / "output"),
            "cache_dir": str(tmp_path / "cache"),
            "log_level": "INFO",
        },
        "seed_inputs": [
            {"type": "pdf", "value": str(p)} for p in PDFS if p.exists()
        ],
        "search": {"providers": ["openalex", "arxiv"]},  # avoid network-bound ones if possible
    })
    rc = run_ingest(cfg)
    assert rc == 0
    rc = run_extract(cfg, no_llm=True)
    assert rc == 0
    rc = run_build_graph(cfg)
    assert rc == 0
    rc = run_analyze(cfg)
    assert rc == 0
    rc = run_generate_report(cfg, no_llm=True)
    assert rc == 0
    report = tmp_path / "output" / "report.md"
    assert report.exists()
    assert "# 1. Scope" in report.read_text()
