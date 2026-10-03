"""Tests for ingestion.backfill.backfill_abstracts."""

from research_graph.ingestion.backfill import backfill_abstracts
from research_graph.models import Paper, ProviderResult
from research_graph.providers import ProviderRegistry


class _FakeProvider:
    """Minimal stand-in exposing only what backfill_abstracts touches."""

    def __init__(self, name, abstracts: dict[str, str], fail: set[str] | None = None):
        self.name = name
        self._abstracts = abstracts
        self._fail = fail or set()
        self.calls: list[str] = []

    def enable(self):
        pass

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        self.calls.append(doi)
        if doi in self._fail:
            return ProviderResult(status="failed", error="boom", source=self.name)
        abstract = self._abstracts.get(doi)
        if abstract is None:
            return ProviderResult(status="ok", data=Paper(paper_id=doi, title="t", abstract=None), source=self.name)
        return ProviderResult(status="ok", data=Paper(paper_id=doi, title="t", abstract=abstract), source=self.name)


def _p(pid, doi=None, abstract=None):
    return Paper(paper_id=pid, title=f"T {pid}", doi=doi, abstract=abstract)


def _registry(*providers):
    return ProviderRegistry(list(providers))


def test_fills_missing_abstract_from_openalex():
    oa = _FakeProvider("openalex", {"10.1/x": "Recovered abstract text."})
    papers = [_p("a", doi="10.1/x"), _p("b", doi="10.2/y")]
    out = backfill_abstracts(papers, _registry(oa))
    assert out[0].abstract == "Recovered abstract text."
    assert out[1].abstract is None
    assert oa.calls == ["10.1/x", "10.2/y"]


def test_does_not_overwrite_existing_abstract():
    oa = _FakeProvider("openalex", {"10.1/x": "Should not be used."})
    out = backfill_abstracts([_p("a", doi="10.1/x", abstract="Already here.")], _registry(oa))
    assert out[0].abstract == "Already here."
    assert oa.calls == []


def test_skips_papers_without_doi():
    oa = _FakeProvider("openalex", {})
    out = backfill_abstracts([_p("a")], _registry(oa))
    assert out[0].abstract is None
    assert oa.calls == []


def test_whitespace_only_abstract_counts_as_missing():
    oa = _FakeProvider("openalex", {"10.1/x": "Filled."})
    out = backfill_abstracts([_p("a", doi="10.1/x", abstract="   ")], _registry(oa))
    assert out[0].abstract == "Filled."


def test_falls_back_to_second_provider_on_failure():
    oa = _FakeProvider("openalex", {"10.1/x": "From OpenAlex."}, fail={"10.1/x"})
    s2 = _FakeProvider("semantic_scholar", {"10.1/x": "From S2."})
    out = backfill_abstracts([_p("a", doi="10.1/x")], _registry(oa, s2))
    assert out[0].abstract == "From S2."


def test_openalex_wins_when_both_available():
    oa = _FakeProvider("openalex", {"10.1/x": "From OpenAlex."})
    s2 = _FakeProvider("semantic_scholar", {"10.1/x": "From S2."})
    out = backfill_abstracts([_p("a", doi="10.1/x")], _registry(oa, s2))
    assert out[0].abstract == "From OpenAlex."
    assert s2.calls == []


def test_records_provenance_of_filled_abstract():
    oa = _FakeProvider("openalex", {"10.1/x": "Filled."})
    out = backfill_abstracts([_p("a", doi="10.1/x")], _registry(oa))
    assert "abstract_from_openalex" in out[0].source_provenance


def test_respects_limit():
    oa = _FakeProvider("openalex", {f"10.{i}/x": f"abs {i}" for i in range(10)})
    papers = [_p(str(i), doi=f"10.{i}/x") for i in range(10)]
    out = backfill_abstracts(papers, _registry(oa), limit=3)
    assert len(oa.calls) == 3
    assert sum(1 for p in out if p.abstract) == 3


def test_no_filler_provider_is_noop():
    out = backfill_abstracts([_p("a", doi="10.1/x")], _registry())
    assert out[0].abstract is None


def test_empty_input():
    assert backfill_abstracts([], _registry()) == []