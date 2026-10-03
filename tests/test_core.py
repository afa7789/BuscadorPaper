"""expansion.core.rank_core orders the graph so the core is the first N papers."""

from research_graph.expansion.core import degree, rank_core
from research_graph.models import Paper

_PRIMARY = "We surveyed 300 participants with a questionnaire and interviews."


def _p(pid, abstract=None, year=2020, cites=0):
    return Paper(paper_id=pid, title=pid, abstract=abstract, year=year,
                 source_provenance={"citation_count": str(cites)})


def test_degree_counts_both_ends():
    links = [{"src": "a", "tgt": "b"}, {"src": "c", "tgt": "b"}]
    assert degree(links) == {"a": 1, "b": 2, "c": 1}


def test_seeds_first_even_when_weak():
    papers = [_p("x", _PRIMARY, cites=99), _p("seed")]
    assert [p.paper_id for p in rank_core(papers, [], {"seed"})] == ["seed", "x"]


def test_primary_before_unknown():
    papers = [_p("u", "An essay."), _p("prim", _PRIMARY)]
    assert [p.paper_id for p in rank_core(papers, [], set())][0] == "prim"


def test_more_connected_wins_among_equals():
    papers = [_p("lone", "x"), _p("hub", "x")]
    links = [{"src": "hub", "tgt": "a"}, {"src": "b", "tgt": "hub"}]
    assert [p.paper_id for p in rank_core(papers, links, set())] == ["hub", "lone"]


def test_ties_broken_by_citations_then_year_then_id():
    papers = [_p("b", "x", year=2019, cites=5), _p("a", "x", year=2019, cites=5),
              _p("c", "x", year=2022, cites=5), _p("d", "x", cites=9)]
    assert [p.paper_id for p in rank_core(papers, [], set())] == ["d", "c", "a", "b"]
