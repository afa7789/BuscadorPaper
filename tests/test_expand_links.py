"""expand_seeds records in-corpus citation links, walks real author ids, honors the cap."""

from research_graph.expansion.citations import ExpandState, expand_seeds
from research_graph.expansion.core import canonical_links
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry
from research_graph.providers.base import ok


def _p(pid, **prov):
    return Paper(paper_id=pid, title=f"paper {pid}", source_provenance=prov)


class _FakeOpenAlex:
    name = "openalex"

    def __init__(self, refs=None, cites=None, works=None):
        self.refs, self.cites, self.works = refs or {}, cites or {}, works or {}
        self.author_calls: list[str] = []

        self.walked: list[str] = []

    def get_references(self, pid):
        self.walked.append(pid)
        return ok(self.refs.get(pid, []), self.name)

    def get_citations(self, pid, limit=50):
        return ok(self.cites.get(pid, []), self.name)

    def get_author_works(self, aid, limit=25):
        self.author_calls.append(aid)
        return ok(self.works.get(aid, []), self.name)


def _expand(fake, seeds, **kw):
    links: list[dict] = []
    kw.setdefault("max_total", None)
    out = expand_seeds(seeds, ProviderRegistry([fake]), min_score=0.0, links=links, **kw)
    return out, links


def test_links_follow_citation_direction(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = _FakeOpenAlex(refs={"s": [_p("r")]}, cites={"s": [_p("c")]})
    out, links = _expand(fake, [_p("s")], max_hops=1)
    assert {p.paper_id for p in out} == {"s", "r", "c"}
    assert {"src": "s", "tgt": "r", "type": "cites"} in links
    assert {"src": "c", "tgt": "s", "type": "cites"} in links


def test_graph_cap_limits_result(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = _FakeOpenAlex(refs={"s": [_p(f"r{i}") for i in range(10)]})
    out, _ = _expand(fake, [_p("s")], max_hops=1, max_total=5)
    assert len(out) == 5


def test_no_cap_keeps_everything(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = _FakeOpenAlex(refs={"s": [_p(f"r{i}") for i in range(10)]})
    out, _ = _expand(fake, [_p("s")], max_hops=1)
    assert len(out) == 11


def test_resume_continues_from_saved_frontier(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = _FakeOpenAlex(refs={"s": [_p("r")], "r": [_p("rr")]})
    state = ExpandState()
    out, _ = _expand(fake, [_p("s")], max_hops=1, state=state)
    assert fake.walked == ["s"]
    assert state.frontier == ["r"] and state.walked == {"s"} and state.hops_done == 1
    out2, _ = _expand(fake, out, max_hops=1, state=state)
    assert fake.walked == ["s", "r"]
    assert "rr" in {p.paper_id for p in out2}
    assert state.hops_done == 2


def test_resume_does_not_repeat_authors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    a1 = {"openalex_author_ids": ["openalex:A1"]}
    fake = _FakeOpenAlex(refs={"s": [_p("r", **a1)], "r": [_p("r2", **a1)]})
    state = ExpandState()
    out, _ = _expand(fake, [_p("s")], max_hops=2, state=state)
    _expand(fake, out, max_hops=2, state=state)
    assert fake.author_calls == ["openalex:A1"]


def test_author_hop_uses_openalex_author_ids(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = _FakeOpenAlex(
        refs={"s": [_p("r", openalex_author_ids=["openalex:A1"])]},
        works={"openalex:A1": [_p("w")]},
    )
    out, _ = _expand(fake, [_p("s")], max_hops=2)
    assert "openalex:A1" in fake.author_calls
    assert "w" in {p.paper_id for p in out}


def test_canonical_links_remaps_merged_ids_and_drops_outside():
    raw = [Paper(paper_id="doi:10.1/a", title="A", doi="10.1/a"),
           Paper(paper_id="openalex:W1", title="A", doi="10.1/a"),
           _p("b")]
    merged = [raw[0], raw[2]]
    links = [{"src": "openalex:W1", "tgt": "b", "type": "cites"},
             {"src": "b", "tgt": "gone", "type": "cites"},
             {"src": "doi:10.1/a", "tgt": "b", "type": "cites"}]
    assert canonical_links(raw, merged, links) == [{"src": "doi:10.1/a", "tgt": "b", "type": "cites"}]


def test_run_expand_writes_links_and_core_first(monkeypatch, tmp_path):
    import json
    from research_graph import expansion
    from research_graph.config import Config

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    seed = {"paper_id": "s", "title": "seed", "source_provenance": {"explicit_seed": "true"}}
    (out / "papers.json").write_text(json.dumps([seed]))
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out)},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "research_scope": {"max_total_papers": 2, "max_graph_papers": 10,
                           "min_relevance_score": 0.0},
        "search": {"expand_by": ["references", "citations"]},
    })
    fake = _FakeOpenAlex(refs={"s": [_p("r1"), _p("r2")]}, cites={"s": [_p("c")]})
    monkeypatch.setattr(expansion, "get_default_registry", lambda c: ProviderRegistry([fake]))
    assert expansion.run_expand(cfg) == 0
    papers = json.loads((out / "papers.json").read_text())
    assert papers[0]["paper_id"] == "s"
    assert len(papers) == 4
    links = json.loads((out / "links.json").read_text())
    assert {"src": "c", "tgt": "s", "type": "cites"} in links
    state = json.loads((out / "expand_state.json").read_text())
    assert state["walked"] == ["c", "r1", "r2", "s"] and state["hops_done"] == 2


def test_run_expand_twice_resumes_and_accumulates_links(monkeypatch, tmp_path):
    import json
    from research_graph import expansion
    from research_graph.config import Config

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "papers.json").write_text(json.dumps([{"paper_id": "s", "title": "seed"}]))
    cfg = Config.model_validate({
        "project": {"name": "t", "output_dir": str(out)},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "research_scope": {"max_hops": 1, "min_relevance_score": 0.0},
        "search": {"expand_by": ["references"]},
    })
    fake = _FakeOpenAlex(refs={"s": [_p("r")], "r": [_p("rr")]})
    monkeypatch.setattr(expansion, "get_default_registry", lambda c: ProviderRegistry([fake]))
    assert expansion.run_expand(cfg) == 0
    assert expansion.run_expand(cfg) == 0
    assert fake.walked == ["s", "r"]
    links = json.loads((out / "links.json").read_text())
    assert {"src": "s", "tgt": "r", "type": "cites"} in links
    assert {"src": "r", "tgt": "rr", "type": "cites"} in links
    assert len(json.loads((out / "papers.json").read_text())) == 3
