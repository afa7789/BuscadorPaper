"""research_graph.providers.base — academic provider contract + RateLimiter.

Every concrete academic data provider (OpenAlex, Semantic Scholar, Crossref,
arXiv, university pages) satisfies this Protocol. Tests can stub providers
without subclassing; the registry accepts any object whose shape matches.

Why Protocol (per CONTEXT.md ADR-lite): third-party clients (httpx-based or
otherwise) can satisfy the contract structurally without inheriting.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from research_graph.models import Author, Institution, Paper


class ProviderResult(BaseModel):
    """Wraps any provider call. ``status`` indicates partial success.

    - status="ok": data is complete and authoritative.
    - status="partial": some fields populated; downstream should merge.
    - status="failed": no data; ``error`` describes why. Pipeline continues.

    ``raw`` holds the raw vendor payload for forensic dumps; ``source`` is the
    provider name (e.g. "openalex") for provenance.
    """

    status: Literal["ok", "partial", "failed"]
    data: Any = None
    error: str | None = None
    source: str
    raw: dict[str, Any] | None = None


@runtime_checkable
class AcademicProvider(Protocol):
    """Every concrete provider exposes ``name`` and these fetch methods.

    Concrete providers may implement only the methods they support; the
    registry fallback short-circuits when methods are missing.
    """

    name: str

    def fetch_by_doi(self, doi: str) -> ProviderResult: ...
    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult: ...
    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult: ...

    async def afetch_by_doi(self, doi: str) -> ProviderResult: ...
    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult: ...

    def get_references(self, paper_id: str) -> ProviderResult: ...
    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult: ...
    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult: ...


class RateLimiter:
    """Simple token-bucket rate limiter.

    Usage:
        limiter = RateLimiter(requests_per_second=2.0)
        await limiter.acquire()    # blocks if needed

    Thread-safe via a Lock so it works under the CLI's single-process async
    fan-out. For multi-process, swap in a sqlite-based limiter (out of scope).
    """

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        self._interval = 1.0 / requests_per_second
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


def ok(data: Any, source: str, *, raw: dict[str, Any] | None = None) -> ProviderResult:
    """Shorthand for a successful result."""
    return ProviderResult(status="ok", data=data, source=source, raw=raw)


def partial(data: Any, source: str, error: str, *, raw: dict[str, Any] | None = None) -> ProviderResult:
    """Shorthand for a partial result with an error message."""
    return ProviderResult(status="partial", data=data, source=source, error=error, raw=raw)


def failed(error: str, source: str, *, raw: dict[str, Any] | None = None) -> ProviderResult:
    """Shorthand for a failed result; never carries data."""
    return ProviderResult(status="failed", source=source, error=error, raw=raw)
