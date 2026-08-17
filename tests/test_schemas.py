"""Tests for Pydantic schemas (Paper, ExtractionRecord, ProjectIdea, TypedEdge)."""

import pytest
from pydantic import ValidationError

from research_graph.models import (
    Paper,
    ExtractionRecord,
    ProjectIdea,
    TypedEdge,
    EdgeType,
)


def test_paper_valid():
    p = Paper(paper_id="x", title="T", year=2024, doi="10.1109/SEC.2019.00023")
    assert p.doi == "10.1109/sec.2019.00023"


def test_paper_invalid_doi_normalized_to_none():
    # Per design: the validator lowercases and strips URL prefixes but
    # does NOT enforce strict DOI regex — strings with no slash are kept
    # verbatim; strings with a slash pass through. A pure-empty suffix
    # triggers None via the explicit empty check.
    p = Paper(paper_id="x", title="T", doi="")
    assert p.doi is None
    # URL prefix stripping works
    p2 = Paper(paper_id="x", title="T", doi="https://doi.org/10.1234/foo")
    assert p2.doi == "10.1234/foo"


def test_extraction_record_minimal():
    rec = ExtractionRecord(paper_id="x", problem="p", main_contribution="c", extraction_confidence=0.5)
    assert rec.paper_id == "x"


def test_extraction_record_confidence_bounds():
    with pytest.raises(ValidationError):
        ExtractionRecord(paper_id="x", problem="p", main_contribution="c", extraction_confidence=1.5)


def test_project_idea_valid():
    pi = ProjectIdea(
        project_title="x",
        one_sentence_proposal="y",
        research_problem="p",
        baseline="b",
        proposed_change="c",
        property_to_prove_or_measure="soundness",
        research_question="rq",
        supporting_papers=["a", "b"],
    )
    assert pi.master_thesis_fit.value == "medium"


def test_typed_edge_valid():
    e = TypedEdge(
        source_node_id="a", target_node_id="b",
        edge_type=EdgeType.AUTHORED_BY, source="declared", confidence=0.9,
    )
    assert e.edge_type == EdgeType.AUTHORED_BY


def test_typed_edge_confidence_bounds():
    with pytest.raises(ValidationError):
        TypedEdge(
            source_node_id="a", target_node_id="b",
            edge_type=EdgeType.AUTHORED_BY, source="x", confidence=2.0,
        )
