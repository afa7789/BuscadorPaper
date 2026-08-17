"""research_graph.llm.base — LLM contract.

Per CONTEXT.md: ``LLMProvider`` is a ``Protocol``, not an ABC. Third-party
SDKs (Anthropic, OpenAI) can satisfy it structurally without inheriting.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResult(BaseModel):
    """Result of a single LLM call. ``structured`` is the parsed JSON when
    ``response_schema`` was supplied AND the provider honored it; otherwise
    callers must fall back to parsing ``content`` themselves.
    """

    content: str
    structured: dict | None = None
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        messages: list[Message],
        *,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResult: ...

    async def acomplete(
        self,
        messages: list[Message],
        *,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResult: ...
