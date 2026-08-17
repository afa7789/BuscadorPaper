"""research_graph.llm.openai_compatible — concrete LLMProvider for any
OpenAI-compatible /chat/completions endpoint (OpenAI, MiniMax, OpenRouter,
Azure OpenAI, vLLM, etc.).

Defensive design: when ``response_schema`` is supplied but the provider
returns non-JSON or invalid JSON, we fall back to a regex extraction over
the prose. If extraction still fails, the LLMResult carries the raw content
and ``structured=None`` — callers handle this defensively.

Caching: optional sqlite cache keyed by canonical SHA-256 of messages+schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx

from research_graph.llm.base import LLMProvider, LLMResult, Message


# Used to extract a JSON object from prose when the provider returned text
# instead of structured JSON (e.g. response_format unsupported).
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _canonical_hash(messages: list[Message], schema: dict | None) -> str:
    payload = {
        "messages": [m.model_dump() for m in messages],
        "schema": schema,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_json_prose(text: str) -> dict | None:
    """Best-effort: find the first {...} block and parse it."""
    if not text:
        return None
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # try trimming trailing junk after the last }
        last = candidate.rfind("}")
        if last > 0:
            try:
                return json.loads(candidate[: last + 1])
            except json.JSONDecodeError:
                return None
        return None


class OpenAICompatibleProvider:
    """Concrete LLMProvider speaking /v1/chat/completions."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        max_retries: int = 3,
        cache: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)
        self._cache = cache

    def _post(self, body: dict) -> dict:
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = RuntimeError(f"transient {resp.status_code}: {resp.text[:200]}")
                    if attempt < self.max_retries:
                        import time
                        time.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                last_err = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise last_err  # type: ignore[misc]

    async def _apost(self, body: dict) -> dict:
        import asyncio
        async with httpx.AsyncClient(timeout=self._client.timeout) as client:
            last_err: Exception | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code in (429, 500, 502, 503, 504):
                        last_err = RuntimeError(f"transient {resp.status_code}: {resp.text[:200]}")
                        if attempt < self.max_retries:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        resp.raise_for_status()
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPError as e:
                    last_err = e
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
            raise last_err  # type: ignore[misc]

    def _build_body(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
        response_schema: dict | None,
    ) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": response_schema, "strict": True},
            }
        return body

    def complete(
        self,
        messages: list[Message],
        *,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResult:
        cache_key = _canonical_hash(messages, response_schema)
        if self._cache is not None:
            hit = self._cache.get(cache_key)
            if hit is not None and hit[0] == "ok":
                cached = hit[1]
                if isinstance(cached, dict):
                    return LLMResult(
                        content=cached.get("content", ""),
                        structured=cached.get("structured"),
                        provider=self.name,
                        prompt_tokens=cached.get("prompt_tokens"),
                        completion_tokens=cached.get("completion_tokens"),
                        cost_usd=cached.get("cost_usd"),
                    )

        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=response_schema,
        )
        data = self._post(body)

        # Extract content + usage
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = ""
        usage = data.get("usage") or {}
        result = LLMResult(
            content=content or "",
            structured=None,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=None,
        )

        # Defensive structured parse: ALWAYS try JSON extraction from prose,
        # even when no schema was requested. Many providers wrap JSON in prose
        # even without response_format, so this is a useful safety net.
        parsed = _extract_json_prose(result.content)
        if parsed is not None:
            result.structured = parsed

        if self._cache is not None:
            try:
                self._cache.set(
                    cache_key,
                    {
                        "content": result.content,
                        "structured": result.structured,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "cost_usd": result.cost_usd,
                    },
                    status="ok",
                    source=self.name,
                )
            except Exception:
                pass

        return result

    async def acomplete(
        self,
        messages: list[Message],
        *,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResult:
        # Cache lookup (sync sqlite3 is OK in async context for a single-process CLI)
        cache_key = _canonical_hash(messages, response_schema)
        if self._cache is not None:
            hit = self._cache.get(cache_key)
            if hit is not None and hit[0] == "ok":
                cached = hit[1]
                if isinstance(cached, dict):
                    return LLMResult(
                        content=cached.get("content", ""),
                        structured=cached.get("structured"),
                        provider=self.name,
                        prompt_tokens=cached.get("prompt_tokens"),
                        completion_tokens=cached.get("completion_tokens"),
                        cost_usd=cached.get("cost_usd"),
                    )

        body = self._build_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=response_schema,
        )
        data = await self._apost(body)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = ""
        usage = data.get("usage") or {}
        result = LLMResult(
            content=content or "",
            structured=None,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=None,
        )
        if response_schema is not None:
            parsed = _extract_json_prose(result.content)
            if parsed is not None:
                result.structured = parsed

        if self._cache is not None:
            try:
                self._cache.set(
                    cache_key,
                    {
                        "content": result.content,
                        "structured": result.structured,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "cost_usd": result.cost_usd,
                    },
                    status="ok",
                    source=self.name,
                )
            except Exception:
                pass

        return result
