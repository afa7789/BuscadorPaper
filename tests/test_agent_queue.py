"""llm.provider: agent — requests queued to disk, answered by the coding agent."""

import json

from research_graph.config import Config
from research_graph.extraction.llm_extraction import extract
from research_graph.llm import AgentQueueProvider, Message, build_default_provider
from research_graph.models import Paper


def _cfg(tmp_path, provider="agent"):
    return Config.model_validate({
        "project": {"name": "t", "output_dir": str(tmp_path / "out"), "cache_dir": str(tmp_path / "c")},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "llm": {"provider": provider},
    })


def test_build_default_provider_returns_agent_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    llm = build_default_provider(_cfg(tmp_path))
    assert isinstance(llm, AgentQueueProvider)
    assert llm.requests == tmp_path / "out" / "agent_llm" / "requests"


def test_unanswered_call_queues_request(tmp_path):
    llm = AgentQueueProvider(tmp_path)
    r = llm.complete([Message(role="user", content="hi")])
    assert r.content == "" and r.structured is None
    [req] = list(llm.requests.glob("*.json"))
    data = json.loads(req.read_text())
    assert data["messages"][0]["content"] == "hi"
    assert data["reply_format"] == "plain text"


def test_answer_is_returned_and_request_removed(tmp_path):
    llm = AgentQueueProvider(tmp_path)
    msgs = [Message(role="user", content="q")]
    llm.complete(msgs, response_schema={"type": "object"})
    [req] = list(llm.requests.glob("*.json"))
    answer = json.loads(req.read_text())["answer_path"]
    with open(answer, "w") as f:
        f.write('{"ok": 1}')
    r = llm.complete(msgs, response_schema={"type": "object"})
    assert r.structured == {"ok": 1}
    assert not req.exists()


def test_extraction_round_trip_fills_open_questions(tmp_path):
    llm = build_default_provider(_cfg(tmp_path))
    paper = Paper(paper_id="doi:10.1/x", title="T", abstract="A", year=2024)
    first = extract(paper, llm)
    assert first.extraction_confidence == 0.0
    [req] = list(llm.requests.glob("*.json"))
    answer = json.loads(req.read_text())["answer_path"]
    with open(answer, "w") as f:
        json.dump({
            "paper_id": "doi:10.1/x", "problem": "p", "main_contribution": "c",
            "extraction_confidence": 0.8,
            "open_questions": [{"statement": "Is X sound?", "confidence": 0.7}],
        }, f)
    second = extract(paper, llm)
    assert second.extraction_confidence == 0.8
    assert second.open_questions[0].problem_hash
