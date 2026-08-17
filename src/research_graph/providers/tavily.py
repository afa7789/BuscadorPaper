"""research_graph.providers.tavily — Tavily web-search provider.

Tavily is an AI-optimized search engine designed for research agents. It
returns ranked results with `url`, `title`, `content` (snippet), and an
optional `raw_content` field with the full extracted text.

Free tier: 1000 requests/month, no per-second cap (only burst limits).
Authenticated via `TAVILY_API_KEY` in the environment.

Use case in this pipeline: DISCOVERY layer — Tavily answers "find me 30
papers on zk-SNARKs for cross-chain light clients" in one call, then the
S2/arxiv/Crossref providers resolve DOIs from the returned URLs. This
solves the OpenAlex rate-limit problem: Tavily's pool is much larger and
designed for AI workloads.

The provider implements the AcademicProvider Protocol by treating
search-by-title as the primary method and providing synthetic fetch_by_doi
that returns partial Paper records when the URL is canonical.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from research_graph.config import Config, lookup_env
from research_graph.models import Paper
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    failed,
    ok,
    partial,
)


_log = logging.getLogger(__name__)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"

# Maps common publisher hostnames to OpenAlex-friendly doi prefixes so we can
# try to extract a DOI from a Tavily URL.
_DOI_IN_URL_RE = re.compile(r"10\.\d{2,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_ID_IN_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{1,5}(?:v\d+)?)", re.IGNORECASE)


def _extract_doi_from_url(url: str) -> str | None:
    m = _DOI_IN_URL_RE.search(url)
    return m.group(0).lower() if m else None


def _extract_arxiv_id_from_url(url: str) -> str | None:
    m = _ARXIV_ID_IN_URL_RE.search(url)
    return m.group(1) if m else None


def _host_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _paper_from_tavily_result(r: dict[str, Any], idx: int) -> Paper:
    """Convert a Tavily search result into a Paper record.

    The Paper's paper_id is built from the URL (canonical) so dedup works
    across Tavily/S2/arXiv later.
    """
    url = r.get("url") or ""
    title = r.get("title") or ""
    content = r.get("content") or r.get("raw_content") or ""
    # Cap content length to keep Paper records small.
    snippet = content[:1500] if content else None
    doi = _extract_doi_from_url(url)
    arxiv = _extract_arxiv_id_from_url(url)
    if doi:
        paper_id = f"doi:{doi}"
    elif arxiv:
        paper_id = f"arxiv:{arxiv}"
    else:
        # Fallback: derive an id from the URL host + path hash.
        paper_id = f"tavily:{idx}:{_host_from_url(url)}"
    return Paper(
        paper_id=paper_id,
        title=title,
        year=None,  # Tavily doesn't return year reliably
        doi=doi,
        urls=[url] if url else [],
        authors=[],  # Tavily doesn't return structured authors
        abstract=snippet,
        venue=_host_from_url(url).replace("www.", ""),
        source_provenance={"tavily": ["title", "url", "content"]},
    )


class TavilyProvider(AcademicProvider):
    """Tavily web search as a discovery layer for academic papers."""

    name = "tavily"

    def __init__(self, config: Config) -> None:
        self._api_key = lookup_env("TAVILY_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Get a free key at "
                "https://tavily.com and add it to your .env file."
            )
        self._client = httpx.Client(timeout=30.0)
        # Soft throttle: Tavily free tier is generous (~1 req/sec sustained)
        # but burst above 5/sec will throttle.
        self._min_interval = 0.25
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _post(self, body: dict) -> ProviderResult:
        self._throttle()
        try:
            resp = self._client.post(
                _TAVILY_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except Exception as e:
            return failed(f"tavily: {e}", self.name)
        if resp.status_code == 401:
            return failed("tavily: invalid API key", self.name)
        if resp.status_code == 429:
            return failed("tavily: rate limited", self.name, raw={"text": resp.text[:200]})
        if resp.status_code != 200:
            return failed(
                f"tavily HTTP {resp.status_code}",
                self.name,
                raw={"text": resp.text[:500]},
            )
        try:
            return ok(resp.json(), self.name, raw=resp.json())
        except Exception as e:
            return failed(f"tavily: bad json: {e}", self.name)

    def _build_query(self, query: str, *, search_depth: str = "advanced") -> dict:
        return {
            "api_key": self._api_key,  # Tavily also accepts it in body
            "query": query,
            "search_depth": search_depth,
            "include_domains": [
                "arxiv.org", "eprint.iacr.org", "iacr.org",
                "openreview.net", "acm.org", "ieee.org",
                "springer.com", "link.springer.com", "sciencedirect.com",
                "usenix.org", "acm.org", "ieee.org",
                "crypto-stackexchange.github.io",
            ],
            "max_results": 20,
            "include_answer": False,
            "include_raw_content": False,
            "topic": "general",
        }

    # --- AcademicProvider protocol methods ----------------------------------

    def search_by_title(self, title: str, limit: int = 10) -> ProviderResult:
        # Slightly augment the query to bias toward papers.
        query = f'"{title}" academic paper research'
        body = self._build_query(query)
        body["max_results"] = limit
        r = self._post(body)
        if r.status != "ok" or not isinstance(r.data, dict):
            return failed(f"tavily search failed: {r.error}", self.name)
        results = r.data.get("results") or []
        papers = [_paper_from_tavily_result(x, i) for i, x in enumerate(results)]
        return ok(papers, self.name, raw=r.data)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        # Tavily doesn't have a direct DOI lookup; use the title heuristic
        # and return partial if the result doesn't match exactly.
        r = self.search_by_title(f'doi:{doi}', limit=1)
        if r.status != "ok" or not r.data:
            return failed(f"tavily: no result for DOI {doi}", self.name)
        return partial(r.data[0] if isinstance(r.data, list) else r.data,
                       self.name, error="tavily has no DOI lookup; returned best match")

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        r = self.search_by_title(f"arxiv {arxiv_id}", limit=3)
        if r.status != "ok" or not r.data:
            return failed(f"tavily: no result for arXiv {arxiv_id}", self.name)
        # Prefer the result whose URL contains arxiv.org/abs/<id>.
        for p in (r.data if isinstance(r.data, list) else []):
            for u in (p.urls or []):
                if f"arxiv.org/abs/{arxiv_id}" in u or arxiv_id in u:
                    return ok(p, self.name, raw=r.data)
        return partial(r.data[0] if isinstance(r.data, list) else r.data,
                       self.name, error=f"tavily: no exact arxiv match for {arxiv_id}")

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    # The methods below return partial/failed because Tavily doesn't expose
    # structured reference/citation/author-graphs. Use S2 or OpenAlex for those.

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("tavily does not expose references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("tavily does not expose citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        # Tavily CAN search by author name; useful as a fallback when
        # OpenAlex/S2 are rate-limited.
        display_name = author_id.split(":", 1)[-1].replace("_", " ").replace("-", " ")
        query = f'author:"{display_name}" recent papers'
        body = self._build_query(query)
        body["max_results"] = limit
        r = self._post(body)
        if r.status != "ok" or not isinstance(r.data, dict):
            return failed(f"tavily author search failed: {r.error}", self.name)
        results = r.data.get("results") or []
        papers = [_paper_from_tavily_result(x, i) for i, x in enumerate(results)]
        return ok(papers, self.name, raw=r.data)
