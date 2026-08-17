"""research_graph.providers.openalex_pdf — best_oa_location PDF finder.

OpenAlex exposes for every work a ``best_oa_location`` field with the
URL the work is most-available from (publisher-hosted PDF, repository,
preprint server). We only download PDFs from sources the legal publisher
chose to make open-access; we do not bypass any paywall.

This provider is OFF by default — activate it with::

    outputs.enable_pdf_download: true
    "openalex" in outputs.pdf_download_providers
    outputs.max_papers_to_download: N

Rate limit: 10 req/s with polite-pool email; 1 req/s without. By default
this provider does not itself query OpenAlex for the work record; it
uses the ``openalex_best_oa_url`` field already stored on Paper. If you
want fresh lookups, use ``fetch_oa_url_by_doi`` after ingest.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

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

_OPENALEX_BASE = "https://api.openalex.org"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class OpenAlexPdfProvider(AcademicProvider):
    """OpenAlex-driven PDF fetcher using best_oa_location.pdf_url.

    For a Paper that already has a direct PDF URL in
    ``source_provenance.openalex_pdf_url`` (set by the main
    OpenAlexProvider when reading the work), this provider downloads
    that PDF directly. Honors polite-pool email if set.
    """

    name = "openalex_pdf"

    def __init__(self, config: Config, cache_dir: Path | None = None) -> None:
        self._email = lookup_env("OPENALEX_EMAIL")
        self._client = httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "research-graph/0.1 (mailto:" + (self._email or "noreply@research-graph.local") + ")"
                )
            },
        )
        if cache_dir is None:
            cache_dir = Path(getattr(config.project, "cache_dir", "./cache")) / "openalex"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._min_interval = 0.5 if self._email else 1.5
        self._last_call = 0.0
        self._enabled = getattr(
            getattr(config, "search", None), "enable_pdf_download", False
        )

    def enable(self) -> None:
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _cache_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._cache_dir / f"{h}.pdf"

    def download_paper_pdf(self, paper: Paper) -> ProviderResult:
        """Try to download the PDF for ``paper`` from its recorded OA URL.

        The PDF URL must already be in paper.source_provenance['openalex_pdf_url'].
        If not, or if download fails, return ``failed`` — caller can try
        Sci-Hub / Anna's Archive next.
        """
        if not self._enabled:
            return failed("openalex_pdf is opt-in (enable_pdf_download: false)", self.name)
        sp = paper.source_provenance or {}
        url = sp.get("openalex_pdf_url") if isinstance(sp, dict) else None
        if not url:
            return failed(
                f"openalex_pdf: no openalex_pdf_url in source_provenance for {paper.paper_id}",
                self.name,
            )
        cached = self._cache_path(str(url))
        if cached.exists():
            sha = _sha256(cached.read_bytes())
            return ok(
                {"paper_id": paper.paper_id, "url": url, "pdf_path": str(cached),
                 "sha256": sha, "size_bytes": cached.stat().st_size, "cached": True},
                self.name,
            )
        self._throttle()
        try:
            resp = self._client.get(str(url))
        except Exception as e:
            return failed(f"openalex_pdf: {e}", self.name, raw={"url": url})
        if resp.status_code != 200:
            return failed(
                f"openalex_pdf: HTTP {resp.status_code} from {url}",
                self.name,
                raw={"url": url, "status": resp.status_code},
            )
        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" not in ctype and "octet-stream" not in ctype:
            return failed(
                f"openalex_pdf: got non-PDF content-type {ctype!r}",
                self.name,
                raw={"url": url},
            )
        data = resp.content
        sha = _sha256(data)
        cached.write_bytes(data)
        return ok(
            {"paper_id": paper.paper_id, "url": url, "pdf_path": str(cached),
             "sha256": sha, "size_bytes": len(data), "cached": False},
            self.name,
        )

    # ----- AcademicProvider protocol: most methods return failed -----

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        return failed("openalex_pdf: use download_paper_pdf(paper) instead", self.name)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("openalex_pdf: arxiv has its own OA path", self.name)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        return failed("openalex_pdf does not search metadata", self.name)

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("openalex_pdf does not list references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("openalex_pdf does not list citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        return failed("openalex_pdf does not list author works", self.name)
