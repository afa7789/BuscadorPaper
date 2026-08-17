"""research_graph.providers.openalex — OpenAlex academic graph client.

OpenAlex is a free, open catalog of the world's scholarly papers. Provides:
- works, authors, institutions, concepts
- references + citations (via works/W123)
- related_works for similarity

API base: https://api.openalex.org
Polite pool: include ?mailto=... for higher rate limits.
"""

from __future__ import annotations

from typing import Any

import httpx

from research_graph.config import Config, lookup_env
from research_graph.models import Author, Paper
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    RateLimiter,
    failed,
    ok,
    partial,
)


def _paper_from_openalex(work: dict[str, Any]) -> Paper:
    """Map a single OpenAlex work object to a Paper record."""
    title = work.get("title") or work.get("display_name") or ""
    doi = (work.get("doi") or "").lower().replace("https://doi.org/", "") or None
    urls: list[str] = []
    if work.get("doi_url"):
        urls.append(work["doi_url"])
    primary_loc = work.get("primary_location") or {}
    primary_source = primary_loc.get("source") or {}
    if primary_source.get("homepage_url"):
        urls.append(primary_source["homepage_url"])
    authors: list[str] = []
    for a in work.get("authorships") or []:
        name = ((a.get("author") or {}).get("display_name"))
        if name:
            authors.append(name)
    venue = primary_source.get("display_name")
    year = work.get("publication_year")
    abstract = work.get("abstract_inverted_index")
    # OpenAlex returns abstracts as inverted indexes; reconstruct a string
    if isinstance(abstract, dict):
        positions: list[tuple[int, str]] = []
        for word, idxs in abstract.items():
            for idx in idxs:
                positions.append((idx, word))
        positions.sort()
        abstract_text = " ".join(w for _, w in positions)
    else:
        abstract_text = None
    raw_id = work.get("id") or doi or title
    # OpenAlex returns the id as a full URL (e.g. "https://openalex.org/W123...");
    # extract the trailing "W<digits>" segment so paper_ids stay short and consistent.
    if raw_id.startswith("http"):
        tail = raw_id.rsplit("/", 1)[-1]
        paper_id = tail if tail else raw_id
    else:
        paper_id = raw_id
    # Capture best_oa_location pdf url when available — this is the
    # open-access PDF link the publisher chose, no paywall bypass.
    provenance: dict[str, Any] = {
        "openalex": ["title", "year", "doi", "authors", "venue"],
    }
    best_oa = work.get("best_oa_location") or {}
    oa_pdf = best_oa.get("pdf_url") or primary_loc.get("pdf_url")
    if oa_pdf:
        provenance["openalex_pdf_url"] = oa_pdf
    return Paper(
        paper_id=f"openalex:{paper_id}" if not paper_id.startswith("openalex:") else paper_id,
        title=title,
        year=year,
        doi=doi,
        urls=urls,
        authors=authors,
        abstract=abstract_text,
        venue=venue,
        source_provenance=provenance,
    )


class OpenAlexProvider(AcademicProvider):
    name = "openalex"

    def __init__(self, config: Config) -> None:
        self._base = "https://api.openalex.org"
        self._mailto = lookup_env("OPENALEX_EMAIL") or "research-graph@example.com"
        self._client = httpx.Client(timeout=30.0)
        self._limiter = RateLimiter(requests_per_second=5.0)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> ProviderResult:
        try:
            qp: dict[str, Any] = {"mailto": self._mailto}
            if params:
                qp.update(params)
            resp = self._client.get(f"{self._base}{path}", params=qp)
            if resp.status_code != 200:
                return failed(f"openalex HTTP {resp.status_code}", self.name, raw={"text": resp.text[:500]})
            data = resp.json()
            return ok(data, self.name, raw=data)
        except Exception as e:
            return failed(str(e), self.name)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        doi_norm = doi.strip().lower().replace("https://doi.org/", "")
        r = self._get(f"/works/doi:{doi_norm}")
        if r.status != "ok" or r.data is None:
            return failed(f"openalex doi lookup failed: {r.error}", self.name)
        return ok(_paper_from_openalex(r.data), self.name, raw=r.data)

    def fetch_work_by_id(self, work_id: str) -> ProviderResult:
        """Fetch a work directly by its OpenAlex id (e.g. 'W4180724' or full URL)."""
        wid = work_id
        if wid.startswith("http"):
            wid = wid.rsplit("/", 1)[-1] or wid
        # OpenAlex: /works/<id> works for W-prefixed ids; reject obviously bad input.
        if not wid.startswith("W"):
            return failed(f"openalex: not a work id: {wid!r}", self.name)
        r = self._get(f"/works/{wid}")
        if r.status != "ok" or r.data is None:
            return failed(f"openalex work fetch failed: {r.error}", self.name)
        return ok(_paper_from_openalex(r.data), self.name, raw=r.data)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        r = self._get(f"/works/doi:10.48550/arXiv.{arxiv_id}")
        if r.status != "ok" or r.data is None:
            return failed(f"openalex arxiv lookup failed: {r.error}", self.name)
        return ok(_paper_from_openalex(r.data), self.name, raw=r.data)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        r = self._get("/works", {"search": title, "per_page": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"openalex title search failed: {r.error}", self.name)
        results = r.data.get("results", [])
        papers = [_paper_from_openalex(w) for w in results]
        return ok(papers, self.name, raw=r.data)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        # paper_id like "openalex:W123..." -> /works/W123
        wid = paper_id.replace("openalex:", "")
        if wid.startswith("http"):
            wid = wid.rsplit("/", 1)[-1] or wid
        r = self._get(f"/works/{wid}")
        if r.status != "ok" or r.data is None:
            return failed(f"openalex refs failed: {r.error}", self.name)
        refs_ids = r.data.get("referenced_works") or []
        # Fetch each reference (capped at 50); strip OpenAlex URL prefix.
        cap = refs_ids[:50]
        out: list[str] = []
        for rid in cap:
            short = rid.rsplit("/", 1)[-1] if isinstance(rid, str) and rid.startswith("http") else rid
            if short:
                out.append(f"openalex:{short}")
        return ok(out, self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        # Use the forward citation endpoint via filter
        wid = paper_id.replace("openalex:", "")
        if wid.startswith("http"):
            wid = wid.rsplit("/", 1)[-1] or wid
        r = self._get("/works", {"filter": f"cites:{wid}", "per_page": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"openalex citants failed: {r.error}", self.name)
        results = r.data.get("results", [])
        # OpenAlex returns work ids as full URLs; strip to "W<digits>".
        out: list[str] = []
        for w in results:
            wid2 = w.get("id")
            if not wid2:
                continue
            short = wid2.rsplit("/", 1)[-1] if isinstance(wid2, str) and wid2.startswith("http") else wid2
            out.append(f"openalex:{short}")
        return ok(out, self.name, raw=r.data)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        aid = author_id.replace("openalex:", "")
        if aid.startswith("http"):
            aid = aid.rsplit("/", 1)[-1] or aid
        r = self._get("/works", {"filter": f"authorships.author.id:{aid}", "per_page": limit})
        if r.status != "ok" or r.data is None:
            return failed(f"openalex author works failed: {r.error}", self.name)
        results = r.data.get("results", [])
        papers = [_paper_from_openalex(w) for w in results]
        return ok(papers, self.name, raw=r.data)
