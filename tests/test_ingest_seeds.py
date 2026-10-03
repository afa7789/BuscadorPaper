"""run_ingest: caps at the graph size and marks the user's explicit seeds."""

import json

from research_graph import ingestion
from research_graph.config import Config
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


def test_ingest_caps_at_graph_and_marks_explicit_seeds(monkeypatch, tmp_path):
    out = tmp_path / "out"
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out)},
        "seed_inputs": [{"type": "doi", "value": "10.1/seed"},
                        {"type": "crossref_query", "value": "q"}],
        "research_scope": {"max_total_papers": 2, "max_graph_papers": 4},
    })
    hits = {
        "doi": [Paper(paper_id="doi:10.1/seed", title="Seed", doi="10.1/seed")],
        "crossref_query": [Paper(paper_id=f"doi:10.1/q{i}", title=f"Q{i}", doi=f"10.1/q{i}")
                           for i in range(6)],
    }
    monkeypatch.setattr(ingestion, "get_default_registry", lambda c: ProviderRegistry())
    monkeypatch.setattr(ingestion, "dispatch", lambda entry, reg: hits[entry.type])
    assert ingestion.run_ingest(cfg, no_llm=True) == 0
    papers = json.loads((out / "papers.json").read_text())
    assert len(papers) == 4
    seeds = [p["paper_id"] for p in papers if p["source_provenance"].get("explicit_seed")]
    assert seeds == ["doi:10.1/seed"]


def test_ingest_without_cap_keeps_all_and_resets_expand(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "expand_state.json").write_text("{}")
    (out / "links.json").write_text("[]")
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out)},
        "seed_inputs": [{"type": "crossref_query", "value": "q"}],
        "research_scope": {"max_total_papers": 2},
    })
    hits = [Paper(paper_id=f"doi:10.1/q{i}", title=f"Q{i}", doi=f"10.1/q{i}") for i in range(6)]
    monkeypatch.setattr(ingestion, "get_default_registry", lambda c: ProviderRegistry())
    monkeypatch.setattr(ingestion, "dispatch", lambda entry, reg: hits)
    assert ingestion.run_ingest(cfg, no_llm=True) == 0
    papers = json.loads((out / "papers.json").read_text())
    assert len(papers) == 6
    assert all(p["source_provenance"].get("ingest_seed") for p in papers)
    assert not (out / "expand_state.json").exists()
    assert not (out / "links.json").exists()
