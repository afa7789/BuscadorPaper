"""research_graph.providers.university_pages — fetch + light-text-extract
official lab / faculty pages for affiliation verification.

This is intentionally minimal: an HTTP GET + simple string-match for the
author name + research line in the page text. It deliberately avoids heavy
HTML parsing or scraping frameworks; the goal is a *signal* for evidence
strength, not a full-text index.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from research_graph.config import Config
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    RateLimiter,
    failed,
    ok,
    partial,
)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


class UniversityPagesProvider(AcademicProvider):
    name = "university_pages"

    def __init__(self, config: Config) -> None:
        self._client = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "research-graph/0.1 (affiliation-verifier)"},
        )
        self._limiter = RateLimiter(requests_per_second=0.5)
        self._homepage_cache: dict[str, str] = {}

    def _verify(self, page_url: str, author_name: str, research_line: str | None) -> ProviderResult:
        try:
            if page_url in self._homepage_cache:
                text = self._homepage_cache[page_url]
            else:
                resp = self._client.get(page_url)
                if resp.status_code != 200:
                    return failed(f"page HTTP {resp.status_code}", self.name)
                text = _strip_html(resp.text[:200_000])  # cap memory
                self._homepage_cache[page_url] = text
            # Look for the author name (case-insensitive) and optionally the research line
            name_lc = author_name.lower()
            text_lc = text.lower()
            name_found = name_lc in text_lc
            line_found = bool(research_line) and research_line.lower() in text_lc
            if name_found and (line_found or research_line is None):
                evidence = {
                    "name_found": True,
                    "line_found": line_found,
                    "snippet": _extract_snippet(text, author_name),
                }
                return ok(evidence, self.name)
            if name_found:
                return partial({"name_found": True, "line_found": False}, self.name,
                              error="name found but research line not confirmed")
            return failed("author name not found on page", self.name)
        except Exception as e:
            return failed(str(e), self.name)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        return failed("university_pages cannot fetch by DOI", self.name)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("university_pages cannot fetch by arxiv", self.name)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        return failed("university_pages does not support title search", self.name)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("university_pages does not expose references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("university_pages does not expose citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        return failed("university_pages does not expose author works", self.name)


def _extract_snippet(text: str, needle: str, window: int = 200) -> str:
    """Return up to ``window`` chars around the first occurrence of needle."""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(needle) + window // 2)
    return text[start:end].strip()
