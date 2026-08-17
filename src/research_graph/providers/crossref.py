"""research_graph.providers.crossref — Crossref DOI metadata client.

Free, no API key. Polite-pool email recommended via env CROSSREF_MAILTO.
"""

from __future__ import annotations

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


def _paper_from_crossref(item: dict[str, Any]) -> Paper:
    doi = (item.get("DOI") or "").lower()
    title_list = item.get("title") or []
    title = title_list[0] if title_list else ""
    authors: list[str] = []
    for a in item.get("author") or []:
        family = a.get("family")
        given = a.get("given")
        if family and given:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
    venue = (item.get("container-title") or [""])[0] or None
    issued = item.get("issued", {}).get("date-parts") or [[None]]
    year = None
    if issued and issued[0]:
        year = issued[0][0]
    urls: list[str] = []
    if doi:
        urls.append(f"https://doi.org/{doi}")
    for u in item.get("URL") or []:
        if u and u not in urls:
            urls.append(u)
    return Paper(
        paper_id=f"doi:{doi}" if doi else title,
        title=title,
        year=year,
        doi=doi or None,
        urls=urls,
        authors=authors,
        venue=venue,
        source_provenance={"crossref": ["title", "year", "doi", "authors", "venue"]},
    )


class CrossrefProvider(AcademicProvider):
    name = "crossref"

    def __init__(self, config: Config) -> None:
        self._base = "https://api.crossref.org"
        self._mailto = lookup_env("CROSSREF_MAILTO") or "research-graph@example.com"
        self._client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": f"research-graph/0.1 (mailto:{self._mailto})"},
        )
        self._limiter = RateLimiter(requests_per_second=5.0)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> ProviderResult:
        try:
            resp = self._client.get(f"{self._base}{path}", params=params or {})
            if resp.status_code == 404:
                return failed("not found", self.name, raw={"text": resp.text[:200]})
            if resp.status_code != 200:
                return failed(f"crossref HTTP {resp.status_code}", self.name, raw={"text": resp.text[:500]})
            return ok(resp.json(), self.name, raw=resp.json())
        except Exception as e:
            return failed(str(e), self.name)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        doi_norm = doi.strip().lower().replace("https://doi.org/", "")
        r = self._get(f"/works/{doi_norm}")
        if r.status != "ok" or r.data is None:
            return failed(f"crossref doi lookup failed: {r.error}", self.name)
        item = (r.data or {}).get("message") or {}
        return ok(_paper_from_crossref(item), self.name, raw=r.data)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        # Crossref does not index arXiv IDs directly. Try the doi wrapper.
        doi_norm = f"10.48550/arXiv.{arxiv_id}"
        return self.fetch_by_doi(doi_norm)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        r = self._get("/works", {"query.title": title, "rows": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"crossref title search failed: {r.error}", self.name)
        items = (r.data or {}).get("message", {}).get("items") or []
        return ok([_paper_from_crossref(it) for it in items], self.name, raw=r.data)

    def search_by_query(self, query: str, limit: int = 20) -> ProviderResult:
        """Free-form query via Crossref query.bibliographic (title+author+year+subject)."""
        r = self._get("/works", {"query.bibliographic": query, "rows": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"crossref query search failed: {r.error}", self.name)
        items = (r.data or {}).get("message", {}).get("items") or []
        return ok([_paper_from_crossref(it) for it in items], self.name, raw=r.data)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        doi = paper_id.replace("doi:", "")
        r = self._get(f"/works/{doi}")
        if r.status != "ok" or r.data is None:
            return failed(f"crossref refs failed: {r.error}", self.name)
        refs = (r.data.get("message") or {}).get("reference") or []
        ids: list[str] = []
        for ref in refs[:50]:
            if ref.get("DOI"):
                ids.append(f"doi:{ref['DOI'].lower()}")
            elif ref.get("unstructured"):
                ids.append(f"unstructured:{ref['unstructured'][:80]}")
        return ok(ids, self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        # Crossref doesn't expose forward citations directly via the free API;
        # return empty list with status="partial".
        return ProviderResult(status="partial", data=[], source=self.name, error="crossref does not expose forward citations")

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        # author_id format: "orcid:XXXX" or "crossref:XXXX" — best-effort
        r = self._get("/works", {"query.author": author_id, "rows": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"crossref author works failed: {r.error}", self.name)
        items = (r.data.get("message") or {}).get("items") or []
        return ok([_paper_from_crossref(it) for it in items], self.name, raw=r.data)
