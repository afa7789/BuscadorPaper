"""research_graph.llm.agent_queue — the coding agent running the pipeline is the LLM.

No API key. Each ``complete`` call is keyed by a hash of (messages, schema):

  - ``answers/<id>.txt`` exists -> return it (JSON parsed into ``structured``).
  - otherwise -> write ``requests/<id>.json`` and return an empty result, so
    the calling stage takes its existing no-LLM fallback.

The agent (opencode, Claude Code, Codex...) answers every file in
``requests/``, then re-runs the stage. Answered requests are removed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.llm.base import LLMResult, Message
from research_graph.llm.openai_compatible import _canonical_hash, _extract_json_prose


_log = logging.getLogger(__name__)


class AgentQueueProvider:
    name = "agent"

    def __init__(self, queue_dir: str | Path) -> None:
        self.queue_dir = Path(queue_dir)
        self.requests = self.queue_dir / "requests"
        self.answers = self.queue_dir / "answers"
        self.requests.mkdir(parents=True, exist_ok=True)
        self.answers.mkdir(parents=True, exist_ok=True)
        self.queued = 0

    def complete(
        self,
        messages: list[Message],
        *,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResult:
        rid = _canonical_hash(messages, response_schema)[:16]
        answer = self.answers / f"{rid}.txt"
        request = self.requests / f"{rid}.json"
        if answer.exists():
            request.unlink(missing_ok=True)
            content = answer.read_text(encoding="utf-8")
            return LLMResult(content=content, structured=_extract_json_prose(content), provider=self.name)
        request.write_text(json.dumps({
            "id": rid,
            "answer_path": str(answer),
            "reply_format": "JSON matching schema" if response_schema else "plain text",
            "max_words": max_tokens // 2,
            "messages": [m.model_dump() for m in messages],
            "schema": response_schema,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        self.queued += 1
        if self.queued == 1:
            _log.warning(f"agent LLM: requests queued in {self.requests}; answer them and re-run this stage")
        return LLMResult(content="", structured=None, provider=self.name)

    async def acomplete(self, messages: list[Message], **kw) -> LLMResult:
        return self.complete(messages, **kw)


__all__ = ["AgentQueueProvider"]
