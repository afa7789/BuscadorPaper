"""OpenAlex provider: author ids, batched references, citants without re-fetch."""

from research_graph.config import Config
from research_graph.models import Paper
from research_graph.providers.base import ok
from research_graph.providers.openalex import OpenAlexProvider, _paper_from_openalex


def _cfg() -> Config:
    return Config.model_validate({
        "project": {"name": "t"},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
    })


def _work(wid: str, authors: list[tuple[str, str]] = ()) -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "title": f"T {wid}",
        "authorships": [
            {"author": {"id": f"https://openalex.org/{aid}", "display_name": name}}
            for aid, name in authors
        ],
    }


def _provider(monkeypatch, responses: dict[str, dict]):
    """Provider whose _get answers from ``responses`` keyed by path and records calls."""
    prov = OpenAlexProvider(_cfg())
    calls: list[tuple[str, dict | None]] = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return ok(responses[path], "openalex")

    monkeypatch.setattr(prov, "_get", fake_get)
    return prov, calls


def test_paper_keeps_openalex_author_ids():
    p = _paper_from_openalex(_work("W1", [("A1", "Alice"), ("A2", "Bob")]))
    assert p.authors == ["Alice", "Bob"]
    assert p.source_provenance["openalex_author_ids"] == ["openalex:A1", "openalex:A2"]


def test_paper_without_authorships_has_no_author_ids():
    assert "openalex_author_ids" not in _paper_from_openalex(_work("W1")).source_provenance


def test_get_citations_returns_papers_in_one_request(monkeypatch):
    prov, calls = _provider(monkeypatch, {"/works": {"results": [_work("W2"), _work("W3")]}})
    r = prov.get_citations("openalex:W1", limit=50)
    assert [p.paper_id for p in r.data] == ["openalex:W2", "openalex:W3"]
    assert all(isinstance(p, Paper) for p in r.data)
    assert calls == [("/works", {"filter": "cites:W1", "per_page": 50})]


def test_get_citations_resolves_doi_seed_to_work_id(monkeypatch):
    prov, calls = _provider(monkeypatch, {
        "/works/doi:10.1/x": _work("W9"),
        "/works": {"results": [_work("W2")]},
    })
    r = prov.get_citations("doi:10.1/x", limit=5)
    assert [p.paper_id for p in r.data] == ["openalex:W2"]
    assert calls[-1] == ("/works", {"filter": "cites:W9", "per_page": 5})


def test_get_references_batches_into_one_lookup(monkeypatch):
    work = _work("W1")
    work["referenced_works"] = [f"https://openalex.org/W{i}" for i in range(10, 13)]
    prov, calls = _provider(monkeypatch, {
        "/works/W1": work,
        "/works": {"results": [_work("W10"), _work("W11"), _work("W12")]},
    })
    r = prov.get_references("openalex:W1")
    assert [p.paper_id for p in r.data] == ["openalex:W10", "openalex:W11", "openalex:W12"]
    assert len(calls) == 2
    assert calls[1] == ("/works", {"filter": "openalex:W10|W11|W12", "per_page": 50})


def test_get_references_without_refs_skips_lookup(monkeypatch):
    prov, calls = _provider(monkeypatch, {"/works/W1": _work("W1")})
    assert prov.get_references("openalex:W1").data == []
    assert len(calls) == 1


def test_api_key_is_sent_when_set(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "k123")
    prov = OpenAlexProvider(_cfg())
    sent: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {}

    def fake_client_get(url, params=None):
        sent.update(params or {})
        return _Resp()

    monkeypatch.setattr(prov._client, "get", fake_client_get)
    prov._get("/works/W1")
    assert sent["api_key"] == "k123"
