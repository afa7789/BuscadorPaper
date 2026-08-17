"""Tests for ingestion.normalize."""

from research_graph.ingestion.normalize import (
    normalize_title,
    normalize_author_name,
    paper_dedup_key,
)


def test_normalize_title_basic():
    assert normalize_title("  The Foo Bar  ") == "the foo bar"


def test_normalize_title_nfc():
    # NFC preserved; case lowered
    assert normalize_title("Über die Kräfte") == "über die kräfte"


def test_normalize_title_empty():
    assert normalize_title("") == ""


def test_normalize_author_name():
    # Use pipe "|" separator (canonical key shape for dedup keys)
    assert normalize_author_name("Smith", "John") == "smith|john"
    # Empty given becomes "smith|-" (canonical empty marker)
    assert normalize_author_name("Smith") == "smith|-"


def test_paper_dedup_key_prefers_doi():
    from research_graph.models import Paper
    p = Paper(paper_id="x", title="Foo", doi="10.1234/ABC")
    assert paper_dedup_key(p) == "10.1234/abc"


def test_paper_dedup_key_falls_back_to_title_author_year():
    from research_graph.models import Paper
    p = Paper(paper_id="x", title="Foo Bar", authors=["John Smith"], year=2024)
    key = paper_dedup_key(p)
    assert "foo bar" in key
    assert "smith" in key
    assert "2024" in key
