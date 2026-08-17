"""research_graph.providers.scihub — fetch full-text PDFs via Sci-Hub.

Sci-Hub exposes an API at https://sci-hub.se/ that resolves DOIs to PDF
download URLs. NO API key required. Sci-Hub has been the target of legal
challenges in the US (see *Sci-Hub v. Elsevier*, 2017) and accessibility
varies by jurisdiction; users should verify their local laws before use.

For research-graph this provider is OPT-IN via a config flag. When enabled,
it is used:
  1. As a fallback when Crossref/S2/arxiv can't get full-text for a seed
  2. As a downstream enrichment step to fill in complete papers

The provider stores downloaded PDFs in ``cache_dir/scihub/`` and indexes them
by SHA-256 so we never re-fetch the same paper.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from research_graph.config import Config
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    failed,
    ok,
    partial,
)


_log = logging.getLogger(__name__)


# Sci-Hub mirror list — multiple so we have fallback if one is down.
# These mirrors come and go; the user may override via env SCIHUB_MIRRORS.
_DEFAULT_MIRRORS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.box",
    "https://sci-hub.fo",
]


# The page at Sci-Hub returns an embed/object pointing to the PDF.
_PDF_LINK_RE = re.compile(
    r'(?:location\.href|src)\s*=\s*[\'"]([^\'"]+\.pdf[^\'"]*)[\'"]',
    re.IGNORECASE,
)
_PDF_DIRECT_RE = re.compile(
    r'(https?://[^\s\'"]+\.pdf)',
    re.IGNORECASE,
)


def _extract_pdf_url(html: str, base: str) -> str | None:
    """Find the PDF URL embedded in the Sci-Hub article page."""
    m = _PDF_DIRECT_RE.search(html)
    if m:
        return m.group(1)
    m = _PDF_LINK_RE.search(html)
    if m:
        url = m.group(1)
        if url.startswith("/"):
            return base.rstrip("/") + url
        return url
    return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SciHubProvider(AcademicProvider):
    """Sci-Hub as full-text PDF source. Optional via config flag."""

    name = "scihub"

    def __init__(self, config: Config, cache_dir: Path | None = None) -> None:
        env_mirrors = os.environ.get("SCIHUB_MIRRORS")
        if env_mirrors:
            self._mirrors = [m.strip() for m in env_mirrors.split(",") if m.strip()]
        else:
            self._mirrors = list(_DEFAULT_MIRRORS)
        if cache_dir is None:
            cache_dir = Path(getattr(config.project, "cache_dir", "./cache")) / "scihub"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/16.0 Safari/605.1.15"
                ),
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._min_interval = 2.0  # polite
        self._last_call = 0.0
        self._enabled = getattr(
            getattr(config, "search", None), "enable_scihub", False
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Allow callers to flip the opt-in flag at runtime."""
        self._enabled = True

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _cache_path(self, doi: str, sha256_hint: str | None = None) -> Path:
        # Hash the DOI for filename safety.
        h = hashlib.sha256(doi.lower().encode()).hexdigest()[:16]
        return self._cache_dir / f"{h}.pdf"

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        """Returns a ProviderResult whose .data = {"doi", "pdf_path", "sha256", "size_bytes"}."""
        if not self._enabled:
            return failed("scihub provider is opt-in (enable_scihub: false in config)", self.name)

        # Local cache hit
        cached = self._cache_path(doi)
        if cached.exists():
            sha = _sha256(cached.read_bytes())
            return ok(
                {"doi": doi.lower(), "pdf_path": str(cached), "sha256": sha,
                 "size_bytes": cached.stat().st_size, "cached": True},
                self.name,
            )

        for mirror in self._mirrors:
            self._throttle()
            url = f"{mirror.rstrip('/')}/{quote(doi)}"
            try:
                resp = self._client.get(url)
            except Exception as e:
                _log.warning(f"scihub {mirror}: connection failed: {e}")
                continue
            if resp.status_code != 200:
                _log.debug(f"scihub {mirror}: HTTP {resp.status_code} for {doi}")
                continue
            # The page might be the redirect HTML or a direct PDF depending on mirror.
            ctype = resp.headers.get("content-type", "")
            if "pdf" in ctype:
                pdf_bytes = resp.content
            else:
                # HTML wrapper; find the real PDF URL
                real = _extract_pdf_url(resp.text, mirror)
                if not real:
                    _log.debug(f"scihub {mirror}: no PDF link in page for {doi}")
                    continue
                self._throttle()
                try:
                    pdf_resp = self._client.get(real)
                except Exception as e:
                    _log.debug(f"scihub mirror: pdf fetch failed: {e}")
                    continue
                if pdf_resp.status_code != 200:
                    continue
                pdf_bytes = pdf_resp.content
            # Save
            sha = _sha256(pdf_bytes)
            cached.write_bytes(pdf_bytes)
            return ok(
                {"doi": doi.lower(), "pdf_path": str(cached), "sha256": sha,
                 "size_bytes": len(pdf_bytes), "cached": False, "mirror": mirror},
                self.name,
            )

        return failed(f"scihub: no mirror returned a PDF for {doi}", self.name)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    # The remaining AcademicProvider methods are intentionally not implemented:
    # Sci-Hub does not have a search API, do not provide bibliographic data,
    # and do not expose references/citations. The methods below return failed.

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("scihub does not have arxiv lookup", self.name)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def search_by_title(self, title: str, limit: int = 10) -> ProviderResult:
        return failed("scihub does not have title search; supply a DOI", self.name)

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("scihub does not expose references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("scihub does not expose citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        return failed("scihub does not expose author graphs", self.name)
