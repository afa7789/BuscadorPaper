"""Tests for ingestion.doi."""

from research_graph.ingestion.doi import parse_doi, extract_doi_from_text, extract_arxiv_from_text


def test_parse_doi_plain():
    assert parse_doi("10.1109/SEC.2019.00023") == "10.1109/sec.2019.00023"


def test_parse_doi_url():
    assert parse_doi("https://doi.org/10.1109/SEC.2019.00023") == "10.1109/sec.2019.00023"


def test_parse_doi_prefix():
    assert parse_doi("doi:10.1109/SEC.2019.00023") == "10.1109/sec.2019.00023"


def test_parse_doi_rejects_garbage():
    assert parse_doi("not a doi") is None
    assert parse_doi("10.1234/") is None
    assert parse_doi("") is None


def test_extract_doi_from_text():
    text = "See Smith et al. (DOI: 10.1234/ABC.XYZ) for details."
    assert extract_doi_from_text(text) == "10.1234/abc.xyz"


def test_extract_arxiv_from_text():
    text = "Preprint arXiv:2401.12345v2 released."
    assert extract_arxiv_from_text(text) == "2401.12345v2"
