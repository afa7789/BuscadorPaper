"""research_graph.providers.annas — Anna's Archive full-text paper fetcher.

Anna's Archive (annas-archive.org) is a shadow library that indexes
Libgen, Sci-Hub, Z-Library and other sources. It has open-access papers
mixed in with books; coverage of CS/crypto papers is real but uneven.

This provider is OPT-IN. To activate it, set:
    outputs.enable_pdf_download: true
    "annas" in outputs.pdf_download_providers
    outputs.max_papers_to_download: N (default 5)

This is a focused / minimal port of /Users/afa/Developer/arthur/book-torrent/
annas_dl.py (340 LOC, full-text book downloader). What we kept:
  - mirror list + TLS-friendly HTTP via curl-not-needed (httpx with
    realistic User-Agent works for AA search)
  - MD5 lookup URL pattern
  - BeautifulSoup parsing for /search?q=... and /md5/<hex>
What we dropped (not needed for paper discovery):
  - book-specific CLI loop
  - libgen mirror fallback chain
  - download progress + resume
  - language/extension filters (we want any kind of full-text)
  - argparse-driven .txt batch mode

HTTP strategy: Anna's Archive sometimes fingerprints non-browser TLS
clients; we keep a generous User-Agent, allow http/2, and fall back to
mirrors. We never bypass rate-limits; if blocked we return ``failed``
honestly instead of forging a result.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from research_graph.config import Config
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    failed,
    ok,
    partial,
)


_log = logging.getLogger(__name__)


AA_MIRRORS = [
    "https://annas-archive.org",
    "https://annas-archive.gl",
    "https://annas-archive.pk",
    "https://annas-archive.gd",
]

# Search returns hit rows; each has an /md5/<hex> anchor for direct lookup.
# We also accept MD5 directly (no search needed).
MD5_PAGE_RE = re.compile(r"/md5/([0-9a-fA-F]{32})")
PDF_LINK_RE = re.compile(
    r'(?:href|src)\s*=\s*[\'"]([^\'"]+\.pdf)',
    re.IGNORECASE,
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AnnasArchiveProvider(AcademicProvider):
    """Full-text fetcher for papers via Anna's Archive.

    Use cases:
      - Search by title (free-text query).
      - Fetch by MD5 hash (32 hex chars).
      - Fetch by DOI string (it is treated as a free-text query since AA
        does not maintain a DOI index).
    """

    name = "annas"

    def __init__(self, config: Config, cache_dir: Path | None = None) -> None:
        self._mirrors = list(AA_MIRRORS)
        if cache_dir is None:
            cache_dir = Path(getattr(config.project, "cache_dir", "./cache")) / "annas"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            },
        )
        self._min_interval = 2.0  # polite
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

    def _get(self, url: str, accept: str = "text/html,application/pdf,*/*") -> tuple[int, str, dict[str, str]]:
        self._throttle()
        try:
            resp = self._client.get(url, headers={"Accept": accept})
        except Exception as e:
            return 0, str(e), {}
        return resp.status_code, resp.text, dict(resp.headers)

    def _cache_path(self, key: str) -> Path:
        h = hashlib.sha256(key.lower().encode()).hexdigest()[:16]
        return self._cache_dir / f"{h}.pdf"

    # ----- public API -----

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        """AA does not index DOIs. Use ``search_by_query`` instead.

        Returns ``failed`` directly so callers can transparently fall back.
        """
        return failed(
            "annas does not expose DOI lookup; use fetch_by_query or fetch_by_arxiv_id",
            self.name,
        )

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        """AA catalogs arXiv preprints. Search for the canonical id."""
        return self.fetch_by_query(f"arXiv:{arxiv_id}")

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        return self.fetch_by_query(title, limit=limit)

    def fetch_by_query(self, query: str, limit: int = 5) -> ProviderResult:
        """Search for ``query`` as free text and return up to ``limit`` MD5s."""
        if not self._enabled:
            return failed("annas provider is opt-in (enable_pdf_download: false)", self.name)
        for base in self._mirrors:
            url = f"{base}/search?q={quote(query)}"
            status, body, _ = self._get(url)
            if status != 200:
                continue
            # Anna's Archive ships some content inside HTML comments;
            # strip them so the parser sees everything.
            body = body.replace("<!--", "").replace("-->", "")
            soup = BeautifulSoup(body, "html.parser")
            md5s: list[str] = []
            titles: list[str] = []
            seen: set[str] = set()
            for a in soup.select('a[href*="/md5/"]'):
                m = MD5_PAGE_RE.search(a.get("href", ""))
                if not m:
                    continue
                md5 = m.group(1).lower()
                if md5 in seen:
                    continue
                seen.add(md5)
                md5s.append(md5)
                t = a.get_text(" ", strip=True)
                if t and len(titles) < limit:
                    titles.append(t[:160])
                if len(md5s) >= limit:
                    break
            if md5s:
                return ok(
                    list(zip(md5s, titles))[:limit],
                    self.name,
                    raw={"query": query, "mirror": base},
                )
        return failed(f"annas: no results for {query!r}", self.name)

    def download_md5(self, md5: str) -> ProviderResult:
        """Resolve an MD5 to a direct PDF and download it.

        Returns ``ProviderResult.data = {md5, pdf_path, sha256, size_bytes}``.
        """
        if not self._enabled:
            return failed("annas provider is opt-in (enable_pdf_download: false)", self.name)
        cached = self._cache_path(md5)
        if cached.exists():
            sha = _sha256(cached.read_bytes())
            return ok(
                {"md5": md5, "pdf_path": str(cached), "sha256": sha,
                 "size_bytes": cached.stat().st_size, "cached": True},
                self.name,
            )

        for base in self._mirrors:
            md5_url = f"{base}/md5/{md5}"
            self._throttle()
            try:
                resp = self._client.get(md5_url)
            except Exception as e:
                _log.debug(f"annas {base} md5 page failed: {e}")
                continue
            if resp.status_code != 200:
                continue
            ctype = resp.headers.get("content-type", "")
            if "pdf" in ctype:
                data = resp.content
            else:
                # HTML page — find a .pdf link
                html = resp.text.replace("<!--", "").replace("-->", "")
                m = PDF_LINK_RE.search(html)
                if not m:
                    continue
                pdf_href = m.group(1)
                if pdf_href.startswith("/"):
                    pdf_href = base + pdf_href
                self._throttle()
                try:
                    pdf_resp = self._client.get(pdf_href)
                except Exception as e:
                    _log.debug(f"annas pdf fetch failed: {e}")
                    continue
                if pdf_resp.status_code != 200:
                    continue
                data = pdf_resp.content
            if len(data) < 1024:
                continue  # probably an error page, not a real PDF
            sha = _sha256(data)
            cached.write_bytes(data)
            return ok(
                {"md5": md5, "pdf_path": str(cached), "sha256": sha,
                 "size_bytes": len(data), "cached": False, "mirror": base},
                self.name,
            )
        return failed(f"annas: md5 {md5} not resolvable", self.name)

    # ----- unsupported AcademicProvider methods -----

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("annas does not expose references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("annas does not expose citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        return failed("annas does not expose author graphs", self.name)
