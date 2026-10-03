"""Tests for ingestion.trim_to_budget — honouring max_total_papers at ingest."""

from research_graph.ingestion import trim_to_budget
from research_graph.models import Paper


def _p(pid, *, abstract=None, year=None, cites=None):
    prov = {"citation_count": [str(cites)]} if cites is not None else {}
    return Paper(paper_id=pid, title=pid, abstract=abstract, year=year, source_provenance=prov)


def test_no_trim_when_under_limit():
    ps = [_p("a"), _p("b")]
    assert trim_to_budget(ps, limit=10, seed_ids=set()) == ps


def test_trim_to_limit():
    ps = [_p(str(i)) for i in range(10)]
    assert len(trim_to_budget(ps, limit=4, seed_ids=set())) == 4


def test_zero_limit_disables_trimming():
    ps = [_p(str(i)) for i in range(10)]
    assert len(trim_to_budget(ps, limit=0, seed_ids=set())) == 10


def test_explicit_seeds_are_never_dropped():
    seed = _p("SEED")
    weak = [_p(f"weak{i}") for i in range(10)]
    kept = trim_to_budget(weak + [seed], limit=3, seed_ids={"SEED"})
    assert "SEED" in {p.paper_id for p in kept}


def test_primary_kept_over_unknown():
    ps = [
        _p("unknown1", abstract="x"),
        _p("primary1", abstract="x"),
        _p("unknown2", abstract="x"),
    ]
    v = {"unknown1": "unknown", "primary1": "primary", "unknown2": "unknown"}
    kept = {p.paper_id for p in trim_to_budget(ps, limit=1, seed_ids=set(), verdicts=v)}
    assert kept == {"primary1"}


def test_abstract_presence_beats_citations():
    # Both primary; the one the LLM can actually read wins.
    ps = [
        _p("cited_noabs", abstract=None, year=2024, cites=999),
        _p("abs_nocite", abstract="text", year=2016, cites=0),
    ]
    v = {"cited_noabs": "primary", "abs_nocite": "primary"}
    kept = {p.paper_id for p in trim_to_budget(ps, limit=1, seed_ids=set(), verdicts=v)}
    assert kept == {"abs_nocite"}


def test_citations_beat_recency():
    ps = [
        _p("new", abstract="t", year=2026, cites=1),
        _p("cited", abstract="t", year=2015, cites=500),
    ]
    v = {"new": "primary", "cited": "primary"}
    kept = {p.paper_id for p in trim_to_budget(ps, limit=1, seed_ids=set(), verdicts=v)}
    assert kept == {"cited"}


def test_preserves_original_order():
    ps = [_p("a", abstract="t", year=2020, cites=1), _p("b"), _p("c", abstract="t", year=2020, cites=99)]
    kept = [p.paper_id for p in trim_to_budget(ps, limit=2, seed_ids=set())]
    assert kept == ["a", "c"]  # 'b' dropped; survivors keep ingest order


def test_tolerates_missing_provenance():
    ps = [_p("a", abstract="t"), _p("b", abstract="t")]
    assert len(trim_to_budget(ps, limit=1, seed_ids=set())) == 1


def test_deterministic_ties():
    ps = [_p("b", abstract="t"), _p("a", abstract="t"), _p("c", abstract="t")]
    v = {p.paper_id: "primary" for p in ps}
    first = [p.paper_id for p in trim_to_budget(ps, limit=2, seed_ids=set(), verdicts=v)]
    ps2 = [_p("c", abstract="t"), _p("a", abstract="t"), _p("b", abstract="t")]
    v2 = {p.paper_id: "primary" for p in ps2}
    second = {p.paper_id for p in trim_to_budget(ps2, limit=2, seed_ids=set(), verdicts=v2)}
    assert set(first) == second