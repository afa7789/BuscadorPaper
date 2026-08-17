"""Tests for ingestion.dedup.merge."""

from research_graph.models import Paper


def _p(pid: str, title: str, doi: str | None = None, abstract: str | None = None, authors=None):
    return Paper(paper_id=pid, title=title, doi=doi, abstract=abstract, authors=authors or [])


def test_merge_by_doi_keeps_first_paper_id():
    a = _p("a", "Foo", doi="10.1/x")
    b = _p("b", "Foo (alt)", doi="10.1/x", abstract="ab")
    out = [p for p in __import__("research_graph.ingestion.dedup", fromlist=["merge"]).merge([a, b])]
    assert len(out) == 1
    assert out[0].paper_id == "a"
    assert out[0].abstract == "ab"


def test_merge_different_dois_kept():
    a = _p("a", "Foo", doi="10.1/x")
    b = _p("b", "Bar", doi="10.2/y")
    out = list(__import__("research_graph.ingestion.dedup", fromlist=["merge"]).merge([a, b]))
    assert len(out) == 2


def test_merge_empty():
    assert list(__import__("research_graph.ingestion.dedup", fromlist=["merge"]).merge([])) == []
