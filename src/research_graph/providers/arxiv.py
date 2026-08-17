"""research_graph.providers.arxiv — arXiv client (no key required).

API base: https://export.arxiv.org/api/query  (Atom XML; we parse with stdlib)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx

from research_graph.config import Config
from research_graph.models import Paper
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    RateLimiter,
    failed,
    ok,
)


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _paper_from_arxiv_entry(entry: ET.Element) -> Paper:
    ns = ATOM_NS
    title_el = entry.find("atom:title", ns)
    title = (title_el.text or "").strip() if title_el is not None else ""
    id_el = entry.find("atom:id", ns)
    arxiv_id = ""
    abs_url = ""
    if id_el is not None and id_el.text:
        # URL like http://arxiv.org/abs/2401.12345v1
        abs_url = id_el.text.strip()
        arxiv_id = abs_url.rsplit("/", 1)[-1]
    summary_el = entry.find("atom:summary", ns)
    abstract = (summary_el.text or "").strip() if summary_el is not None else None
    published_el = entry.find("atom:published", ns)
    year = None
    if published_el is not None and published_el.text:
        year = int(published_el.text[:4])
    authors: list[str] = []
    for a in entry.findall("atom:author", ns):
        name_el = a.find("atom:name", ns)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())
    doi_el = entry.find("arxiv:doi", ns)
    doi = (doi_el.text or "").strip().lower() if doi_el is not None and doi_el.text else None
    urls: list[str] = []
    if abs_url:
        urls.append(abs_url)
    pdf_link = None
    for link in entry.findall("atom:link", ns):
        if link.attrib.get("title") == "pdf" or link.attrib.get("rel") == "related":
            pdf_link = link.attrib.get("href")
            break
    if pdf_link:
        urls.append(pdf_link)
    if doi:
        urls.append(f"https://doi.org/{doi}")
    return Paper(
        paper_id=f"arxiv:{arxiv_id}",
        title=title,
        year=year,
        doi=doi,
        urls=urls,
        authors=authors,
        abstract=abstract,
        source_provenance={"arxiv": ["title", "year", "authors", "abstract"]},
    )


class ArxivProvider(AcademicProvider):
    name = "arxiv"

    def __init__(self, config: Config) -> None:
        self._base = "https://export.arxiv.org/api/query"
        self._client = httpx.Client(timeout=30.0)
        self._limiter = RateLimiter(requests_per_second=1.0)  # arXiv ToS: 1 req/3s

    def _get(self, params: dict[str, Any]) -> ProviderResult:
        try:
            resp = self._client.get(self._base, params=params)
            if resp.status_code != 200:
                return failed(f"arxiv HTTP {resp.status_code}", self.name, raw={"text": resp.text[:500]})
            root = ET.fromstring(resp.text)
            return ok(root, self.name, raw={"text": resp.text[:5000]})
        except Exception as e:
            return failed(str(e), self.name)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        # arXiv indexes papers by arXiv id, not DOI. Best-effort: search.
        return self.search_by_title(doi, limit=1)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        r = self._get({"id_list": arxiv_id})
        if r.status != "ok" or r.data is None:
            return failed(f"arxiv id lookup failed: {r.error}", self.name)
        entries = r.data.findall("atom:entry", ATOM_NS)
        if not entries:
            return failed("arxiv id not found", self.name)
        return ok(_paper_from_arxiv_entry(entries[0]), self.name, raw=r.data)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        # arXiv query: ti:"exact phrase" or all:word1 word2
        q = f"ti:{title}"
        r = self._get({"search_query": q, "max_results": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"arxiv title search failed: {r.error}", self.name)
        entries = r.data.findall("atom:entry", ATOM_NS)
        papers = [_paper_from_arxiv_entry(e) for e in entries]
        return ok(papers, self.name, raw=r.data)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        # arXiv does not provide structured references via this API
        return ProviderResult(status="partial", data=[], source=self.name, error="arxiv does not expose structured references")

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return ProviderResult(status="partial", data=[], source=self.name, error="arxiv does not expose forward citations")

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        # author_id expected as "arxiv:Lastname_F" (arXiv-style)
        name = author_id.replace("arxiv:", "").replace("_", " ")
        r = self._get({"search_query": f"au:{name}", "max_results": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"arxiv author works failed: {r.error}", self.name)
        entries = r.data.findall("atom:entry", ATOM_NS)
        return ok([_paper_from_arxiv_entry(e) for e in entries], self.name, raw=r.data)
