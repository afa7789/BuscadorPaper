"""research_graph.providers.semantic_scholar — Semantic Scholar Academic Graph client.

Provides: paper lookup (by DOI/arXiv/title), references, citations, recommendations.
Free tier: 100 req / 5 min unauthenticated; with API key much higher.

API base: https://api.semanticscholar.org/graph/v1
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from research_graph.config import Config, lookup_env
from research_graph.models import Paper
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    RateLimiter,
    failed,
    ok,
)


_PAPER_FIELDS = ",".join([
    "paperId", "externalIds", "title", "abstract", "year", "venue",
    "publicationVenue", "authors", "citationCount", "referenceCount",
])

# Endpoints that don't accept the `fields` query param (S2 rejects 400 otherwise).
_NO_FIELDS_PATHS = (
    "/author/search",
    "/paper/search",
    "/paper/auto-search",
)


def _paper_from_s2(p: dict[str, Any]) -> Paper:
    ext = p.get("externalIds") or {}
    doi = ext.get("DOI")
    arxiv = ext.get("ArXiv")
    s2_id = p.get("paperId") or ""
    paper_id = (
        f"s2:{s2_id}" if s2_id else
        (f"doi:{doi.lower()}" if doi else f"arxiv:{arxiv}" if arxiv else p.get("title", ""))
    )
    urls: list[str] = []
    if doi:
        urls.append(f"https://doi.org/{doi.lower()}")
    if arxiv:
        urls.append(f"https://arxiv.org/abs/{arxiv}")
    authors = [a.get("name", "") for a in (p.get("authors") or []) if a.get("name")]
    venue = p.get("venue") or (p.get("publicationVenue") or {}).get("name")
    return Paper(
        paper_id=paper_id,
        title=p.get("title") or "",
        year=p.get("year"),
        doi=(doi or "").lower() or None,
        urls=urls,
        authors=authors,
        abstract=p.get("abstract"),
        venue=venue,
        source_provenance={"semantic_scholar": ["title", "year", "doi", "authors", "venue"]},
    )


class SemanticScholarProvider(AcademicProvider):
    name = "semantic_scholar"

    _log = logging.getLogger(__name__)

    def __init__(self, config: Config) -> None:
        self._base = "https://api.semanticscholar.org/graph/v1"
        self._client = httpx.Client(timeout=30.0)
        self._api_key = lookup_env("SEMANTIC_SCHOLAR_API_KEY")
        # S2 ToS: <=100 req / 5 min without key (~0.33/s); with key ~1 req/s.
        self._min_interval = 0.3 if self._api_key else 3.5  # seconds between calls
        self._last_call = 0.0

    def _throttle(self) -> None:
        import time
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["x-api-key"] = self._api_key
        return h

    def _get(self, path: str, params: dict[str, Any] | None = None) -> ProviderResult:
        import time
        self._throttle()
        last_err: str | None = None
        for attempt in range(3):  # 3 attempts total
            try:
                qp: dict[str, Any] = {}
                # Only attach paper fields to endpoints that accept them.
                if not any(path.startswith(p) for p in _NO_FIELDS_PATHS):
                    qp["fields"] = _PAPER_FIELDS
                if params:
                    qp.update(params)
                resp = self._client.get(f"{self._base}{path}", params=qp, headers=self._headers())
                if resp.status_code == 404:
                    return failed("not found", self.name, raw={"text": resp.text[:200]})
                if resp.status_code == 429:
                    last_err = f"s2 HTTP 429 (rate limit): {resp.text[:200]}"
                    wait = 5 * (attempt + 1)  # 5s, 10s, 15s
                    self._log.warning(f"s2 rate limited on {path}, waiting {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    return failed(f"s2 HTTP {resp.status_code}", self.name, raw={"text": resp.text[:500]})
                return ok(resp.json(), self.name, raw=resp.json())
            except Exception as e:
                last_err = str(e)
                time.sleep(1 + attempt)
        return failed(last_err or "s2: exhausted retries", self.name)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        doi_norm = doi.strip().lower().replace("https://doi.org/", "")
        r = self._get(f"/paper/DOI:{doi_norm}")
        if r.status != "ok" or r.data is None:
            return failed(f"s2 doi lookup failed: {r.error}", self.name)
        return ok(_paper_from_s2(r.data), self.name, raw=r.data)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        r = self._get(f"/paper/arXiv:{arxiv_id}")
        if r.status != "ok" or r.data is None:
            return failed(f"s2 arxiv lookup failed: {r.error}", self.name)
        return ok(_paper_from_s2(r.data), self.name, raw=r.data)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        r = self._get("/paper/search", {"query": title, "limit": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"s2 title search failed: {r.error}", self.name)
        results = (r.data or {}).get("data", [])
        return ok([_paper_from_s2(p) for p in results], self.name, raw=r.data)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        # paper_id like "s2:abcdef..." or just the id
        pid = paper_id.replace("s2:", "")
        r = self._get(f"/paper/{pid}/references", {"fields": "paperId,externalIds"})
        if r.status != "ok" or r.data is None:
            return failed(f"s2 refs failed: {r.error}", self.name)
        cited = r.data.get("citedPapers") or []
        ids: list[str] = []
        for c in cited[:50]:
            p = c.get("paper") or {}
            ext = p.get("externalIds") or {}
            if p.get("paperId"):
                ids.append(f"s2:{p['paperId']}")
            elif ext.get("DOI"):
                ids.append(f"doi:{ext['DOI'].lower()}")
            elif ext.get("ArXiv"):
                ids.append(f"arxiv:{ext['ArXiv']}")
        return ok(ids, self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        pid = paper_id.replace("s2:", "")
        r = self._get(f"/paper/{pid}/citations", {"fields": "paperId,externalIds", "limit": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"s2 citants failed: {r.error}", self.name)
        citing = r.data.get("citingPapers") or []
        ids: list[str] = []
        for c in citing[:limit]:
            ext = c.get("externalIds") or {}
            if c.get("paperId"):
                ids.append(f"s2:{c['paperId']}")
            elif ext.get("DOI"):
                ids.append(f"doi:{ext['DOI'].lower()}")
            elif ext.get("ArXiv"):
                ids.append(f"arxiv:{ext['ArXiv']}")
        return ok(ids, self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        aid = author_id.replace("s2:", "")
        r = self._get(f"/author/{aid}/papers", {"fields": _PAPER_FIELDS, "limit": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"s2 author works failed: {r.error}", self.name)
        results = r.data.get("data", [])
        return ok([_paper_from_s2(p) for p in results], self.name, raw=r.data)
