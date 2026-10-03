"""Tests for the Crossref provider's abstract extraction and work filters."""

from research_graph.config import Config, load_config
from research_graph.providers.crossref import CrossrefProvider, _clean_abstract


def _cfg(tmp_path, **scope) -> Config:
    research_scope = {
        "seed_keywords": [],
        "max_hops": 2,
        "max_papers_per_query": 40,
        "max_total_papers": 100,
        "years_from": 2015,
        "years_to": 2026,
        "min_relevance_score": 0.45,
        **scope,
    }
    return Config.model_validate({
        "project": {"name": "t"},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "research_scope": research_scope,
    })


# ---------- _clean_abstract --------------------------------------------------

def test_clean_abstract_strips_jats_tags():
    raw = "<jats:p>Background: abuse is common.</jats:p><jats:p>Methods: survey.</jats:p>"
    assert _clean_abstract(raw) == "Background: abuse is common. Methods: survey."


def test_clean_abstract_unescapes_entities():
    assert _clean_abstract("<p>Tom &amp; Jerry\u2019s study</p>") == "Tom & Jerry\u2019s study"


def test_clean_abstract_collapses_whitespace():
    assert _clean_abstract("<p>a\n\n   b</p>") == "a b"


def test_clean_abstract_returns_none_for_empty():
    assert _clean_abstract(None) is None
    assert _clean_abstract("") is None
    assert _clean_abstract("<jats:p> </jats:p>") is None


def test_clean_abstract_handles_tag_only():
    assert _clean_abstract("<jats:title/>") is None


# ---------- _work_filter -----------------------------------------------------

def test_work_filter_is_journal_articles_within_year_window():
    p = CrossrefProvider(_cfg(None))
    f = p._work_filter()
    assert "type:journal-article" in f
    assert "from-pub-date:2015-01-01" in f
    assert "until-pub-date:2026-12-31" in f


def test_work_filter_omits_missing_year_bounds():
    # Config types years_from/years_to as int, so a None can only reach the
    # provider from a non-Config stub. The guard must still hold.
    from types import SimpleNamespace

    stub = SimpleNamespace(research_scope=SimpleNamespace(years_from=None, years_to=None))
    assert CrossrefProvider(stub)._work_filter() == "type:journal-article"


# ---------- _paper_from_crossref ---------------------------------------------

def test_paper_from_crossref_carries_abstract():
    from research_graph.providers.crossref import _paper_from_crossref

    item = {
        "DOI": "10.1080/10538712.2014.929607",
        "title": ["Child Sexual Abuse in the Context of the Roman Catholic Church"],
        "abstract": "<jats:p>A systematic literature review.</jats:p>",
        "issued": {"date-parts": [[2014]]},
        "author": [{"given": "Bettina", "family": "Bohm"}],
        "container-title": ["Journal of Child Sexual Abuse"],
        "is-referenced-by-count": 42,
    }
    p = _paper_from_crossref(item)
    assert p.abstract == "A systematic literature review."
    assert p.year == 2014
    assert p.doi == "10.1080/10538712.2014.929607"
    assert p.venue == "Journal of Child Sexual Abuse"
    assert p.authors == ["Bettina Bohm"]


def test_paper_from_crossref_abstract_none_when_absent():
    from research_graph.providers.crossref import _paper_from_crossref

    p = _paper_from_crossref({"DOI": "10.1/x", "title": ["T"], "issued": {"date-parts": [[2020]]}})
    assert p.abstract is None