"""run_extract sends only the core (first max_total_papers) to the LLM."""

import json

from research_graph import extraction
from research_graph.config import Config
from research_graph.models import ExtractionRecord


def test_llm_only_for_core(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "papers.json").write_text(json.dumps(
        [{"paper_id": f"p{i}", "title": f"T{i}"} for i in range(5)]))
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out)},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "research_scope": {"max_total_papers": 2, "max_graph_papers": 5},
    })
    llm_calls: list[str] = []

    def fake_extract(p, llm):
        llm_calls.append(p.paper_id)
        return ExtractionRecord(paper_id=p.paper_id, extraction_confidence=0.9)

    monkeypatch.setattr(extraction, "build_default_provider", lambda c: object())
    monkeypatch.setattr(extraction, "llm_extract", fake_extract)
    monkeypatch.setattr(extraction, "classify", lambda rec, llm: rec)
    assert extraction.run_extract(cfg) == 0
    assert llm_calls == ["p0", "p1"]
    recs = json.loads((out / "extractions.json").read_text())
    assert [r["paper_id"] for r in recs] == [f"p{i}" for i in range(5)]
