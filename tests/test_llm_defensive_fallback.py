"""Tests that the LLM defensive fallback returns structured=None when content is non-JSON."""

from research_graph.llm.base import LLMResult, Message
from research_graph.llm.openai_compatible import OpenAICompatibleProvider


class _StubProvider:
    """Stand-in for OpenAICompatibleProvider's HTTP behavior."""
    def __init__(self, response_data):
        self._data = response_data
        self.calls = 0

    def _post(self, body):
        self.calls += 1
        return self._data


def test_defensive_fallback_extracts_json_from_prose(monkeypatch):
    """If the LLM returns prose containing JSON, the provider extracts it."""
    provider = OpenAICompatibleProvider(api_key="x", model="m", base_url="http://stub")
    stub = _StubProvider({
        "choices": [{"message": {"content": 'Here is the JSON: {"problem": "x", "main_contribution": "y", "extraction_confidence": 0.7}'}}],
        "usage": {},
    })
    monkeypatch.setattr(provider, "_post", stub._post)
    r = provider.complete([Message(role="user", content="hi")])
    assert r.structured is not None
    assert r.structured["problem"] == "x"


def test_defensive_fallback_returns_structured_none_on_garbage(monkeypatch):
    provider = OpenAICompatibleProvider(api_key="x", model="m", base_url="http://stub")
    stub = _StubProvider({
        "choices": [{"message": {"content": "Sorry, I cannot help with that."}}],
        "usage": {},
    })
    monkeypatch.setattr(provider, "_post", stub._post)
    r = provider.complete([Message(role="user", content="hi")])
    assert r.structured is None
