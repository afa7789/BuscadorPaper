"""search.expand_by gates which expansion axes expand_seeds walks."""

from research_graph.expansion import citations
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


def _run(monkeypatch, expand_by):
    calls: list[str] = []
    monkeypatch.setattr(citations, "collect_references",
                        lambda *a, **k: calls.append("references") or [])
    monkeypatch.setattr(citations, "collect_citations",
                        lambda *a, **k: calls.append("citations") or [])
    seed = Paper(paper_id="doi:10.1/x", title="Seed")
    citations.expand_seeds([seed], ProviderRegistry(), max_hops=1, expand_by=expand_by)
    return calls


def test_default_walks_refs_and_citations(monkeypatch):
    assert _run(monkeypatch, None) == ["references", "citations"]


def test_only_references(monkeypatch):
    assert _run(monkeypatch, ["references"]) == ["references"]


def test_only_citations(monkeypatch):
    assert _run(monkeypatch, ["citations"]) == ["citations"]


def test_run_expand_passes_config_expand_by(monkeypatch, tmp_path):
    import json
    from research_graph import expansion
    from research_graph.config import Config

    out = tmp_path / "out"
    out.mkdir()
    (out / "papers.json").write_text(json.dumps([{"paper_id": "doi:10.1/x", "title": "S"}]))
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out), "cache_dir": str(tmp_path / "c")},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "search": {"expand_by": ["citations"]},
    })
    seen = {}
    monkeypatch.setattr(expansion, "get_default_registry", lambda c: ProviderRegistry())
    monkeypatch.setattr(expansion, "expand_seeds",
                        lambda *a, **k: seen.update(k) or [])
    assert expansion.run_expand(cfg) == 0
    assert seen["expand_by"] == ["citations"]
