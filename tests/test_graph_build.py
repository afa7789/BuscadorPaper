"""Tests for graph.build.assemble."""

import networkx as nx

from research_graph.graph.build import assemble
from research_graph.models import (
    Author,
    ExtractionRecord,
    Institution,
    Paper,
)


def test_assemble_paper_author_concept_edges():
    papers = [
        Paper(paper_id="p1", title="A", authors=["Alice", "Bob"]),
        Paper(paper_id="p2", title="B", authors=["Alice", "Carol"]),
    ]
    records = [
        ExtractionRecord(
            paper_id="p1", problem="x", main_contribution="y",
            research_area=["crypto"], extraction_confidence=0.7,
        ),
        ExtractionRecord(
            paper_id="p2", problem="x", main_contribution="y",
            research_area=["crypto"], extraction_confidence=0.7,
        ),
    ]
    g = assemble(papers, records=records)
    assert g.has_node("p1")
    assert g.has_node("p2")
    assert g.has_node("name:alice")
    # Both papers cite Alice
    authored_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("edge_type") == "AUTHORED_BY"]
    assert ("p1", "name:alice") in authored_edges
    assert ("p2", "name:alice") in authored_edges
    # Concept edge present
    assert any(d.get("edge_type") == "SHARES_CONCEPT" for _, _, d in g.edges(data=True))


def test_assemble_node_types():
    papers = [Paper(paper_id="p1", title="A", authors=[])]
    g = assemble(papers)
    assert g.nodes["p1"]["node_type"] == "paper"


def test_assemble_empty():
    g = assemble([])
    assert g.number_of_nodes() == 0
