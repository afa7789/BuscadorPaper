"""research_scope.max_graph_papers: graph cap, falls back to max_total_papers."""

from research_graph.config import Config


def _scope(**kw):
    return Config.model_validate({
        "project": {"name": "t"},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "research_scope": kw,
    }).research_scope


def test_graph_has_no_cap_by_default():
    assert _scope(max_total_papers=100).graph_cap is None


def test_graph_cap_uses_max_graph_papers():
    s = _scope(max_total_papers=100, max_graph_papers=1000)
    assert (s.max_total_papers, s.graph_cap) == (100, 1000)
