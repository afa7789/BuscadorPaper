"""OpenProblem.problem_hash is computed in code, never asked of the LLM."""

import hashlib

from research_graph.llm.prompts import EXTRACT_SYSTEM
from research_graph.models import ExtractionRecord, OpenProblem


def test_hash_computed_from_statement():
    op = OpenProblem(statement="  Is  Groth16 post-quantum?  ", confidence=0.6)
    expected = hashlib.sha1("is groth16 post-quantum?".encode("utf-8")).hexdigest()
    assert op.problem_hash == expected


def test_llm_supplied_hash_is_overwritten():
    a = OpenProblem(statement="Open X", problem_hash="garbage", confidence=0.5)
    b = OpenProblem(statement="open   x", confidence=0.5)
    assert a.problem_hash == b.problem_hash


def test_schema_sent_to_llm_does_not_require_hash():
    schema = ExtractionRecord.model_json_schema()
    required = schema["$defs"]["OpenProblem"].get("required", [])
    assert "problem_hash" not in required


def test_extract_prompt_asks_for_open_questions():
    assert "open_questions" in EXTRACT_SYSTEM


def test_extraction_cache_key_depends_on_prompt(monkeypatch):
    from research_graph.extraction import llm_extraction
    from research_graph.models import Paper

    paper = Paper(paper_id="x", title="T")
    before = llm_extraction._cache_key(paper)
    monkeypatch.setattr(llm_extraction, "EXTRACT_SYSTEM", "changed")
    assert llm_extraction._cache_key(paper) != before
