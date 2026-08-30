"""research_graph.providers.scidb — Anna's Archive SciDB full-text fetcher by DOI.

SciDB (https://annas-archive.org/scidb/<doi>) is the continuation of
Sci-Hub: same collection plus post-2022 papers, direct PDF viewing.
Unlike the generic Anna's Archive search (providers/annas.py), SciDB is
a **DOI index**, so no fuzzy title matching is needed.

Transport: Anna's Archive sits behind DDoS-Guard, which fingerprints
TLS. We prefer ``curl_cffi`` (Chrome impersonation) when installed and
fall back to httpx. When DDoS-Guard still serves its JS challenge, we
fail honestly with instructions: open the site once in a real browser
and export the ``__ddg*`` cookies via the AA_COOKIES env var
(``AA_COOKIES="__ddg1_=...; __ddg2_=..."``).

Opt-in like the other download providers:
    outputs.enable_pdf_download: true
    "scidb" in outputs.pdf_download_providers
Mirrors overridable via AA_MIRRORS (comma-separated).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin

from research_graph.config import Config
from research_graph.providers.base import AcademicProvider, ProviderResult, failed, ok


_log = logging.getLogger(__name__)

_DEFAULT_MIRRORS = [
    "https://annas-archive.org",
    "https://annas-archive.gl",
    "https://annas-archive.pk",
    "https://annas-archive.gd",
]

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Direct pdf links and the md5 page link SciDB renders for external downloads.
_PDF_LINK_RE = re.compile(r'(?:href|src)\s*=\s*[\'"]([^\'"]+\.pdf[^\'"]*)[\'"]', re.IGNORECASE)
_MD5_LINK_RE = re.compile(r'href\s*=\s*[\'"][^\'"]*/md5/([0-9a-fA-F]{32})')
_DDOS_MARKER = "DDoS-Guard"

_COOKIE_HELP = (
    "scidb blocked by DDoS-Guard on all mirrors; open any annas-archive "
    "mirror once in your browser, copy the Cookie header (the __ddg* values) "
    "and export AA_COOKIES='__ddg1_=...; __ddg2_=...' in .env"
)


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
    """GET with curl_cffi Chrome impersonation when available, httpx otherwise."""
    try:
        from curl_cffi import requests as cffi_requests

        r = cffi_requests.get(url, headers=headers, impersonate="chrome",
                              timeout=60, allow_redirects=True)
        return r.status_code, r.content, {k.lower(): v for k, v in r.headers.items()}
    except ImportError:
        pass
    except Exception as e:
        return 0, str(e).encode(), {}
    import httpx

    try:
        r = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
        return r.status_code, r.content, {k.lower(): v for k, v in r.headers.items()}
    except Exception as e:
        return 0, str(e).encode(), {}


class SciDBProvider(AcademicProvider):
    """Fetch full-text paper PDFs from Anna's Archive SciDB by DOI."""

    name = "scidb"

    def __init__(self, config: Config, cache_dir: Path | None = None) -> None:
        env_mirrors = os.environ.get("AA_MIRRORS", "").strip()
        if env_mirrors:
            self._mirrors = [m.strip() for m in env_mirrors.split(",") if m.strip()]
        else:
            self._mirrors = list(_DEFAULT_MIRRORS)
        if cache_dir is None:
            cache_dir = Path(getattr(config.project, "cache_dir", "./cache")) / "scidb"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cookies = os.environ.get("AA_COOKIES", "").strip()
        self._dead: set[str] = set()      # mirrors that failed to resolve/connect
        self._blocked: set[str] = set()   # mirrors serving the DDoS-Guard challenge
        self._min_interval = 2.0  # polite
        self._last_call = 0.0
        self._enabled = getattr(
            getattr(config, "outputs", None), "enable_pdf_download", False
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _headers(self) -> dict[str, str]:
        h = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._cookies:
            h["Cookie"] = self._cookies
        return h

    def _get(self, url: str) -> tuple[int, bytes, dict[str, str]]:
        self._throttle()
        return _http_get(url, self._headers())

    def _cache_path(self, doi: str) -> Path:
        h = hashlib.sha256(doi.lower().encode()).hexdigest()[:16]
        return self._cache_dir / f"{h}.pdf"

    def _extract_pdf_url(self, html: str, base: str) -> str | None:
        m = _PDF_LINK_RE.search(html)
        if m:
            return urljoin(base + "/", m.group(1))
        return None

    def _ok_pdf(self, doi: str, cached: Path, data: bytes, mirror: str) -> ProviderResult:
        cached.write_bytes(data)
        return ok(
            {"doi": doi, "pdf_path": str(cached),
             "sha256": hashlib.sha256(data).hexdigest(),
             "size_bytes": len(data), "cached": False, "mirror": mirror},
            self.name,
        )

    def _live_mirrors(self) -> list[str]:
        return [m for m in self._mirrors if m not in self._dead and m not in self._blocked]

    def _is_pdf(self, status: int, ctype: str, body: bytes) -> bool:
        return status == 200 and len(body) >= 1024 and (
            "pdf" in ctype or body[:5] == b"%PDF-"
        )

    def _try_mirror(self, base: str, doi: str) -> bytes | None:
        """One mirror attempt; marks dead/blocked mirrors as a side effect."""
        url = f"{base}/scidb/{quote(doi, safe='/')}/"
        status, body, headers = self._get(url)
        if status == 0:
            self._dead.add(base)  # DNS/connect failure: skip for the whole run
            return None
        ctype = headers.get("content-type", "").lower()
        if self._is_pdf(status, ctype, body):
            return body
        html = body.decode("utf-8", errors="replace")
        if _DDOS_MARKER in html:
            self._blocked.add(base)  # challenge is per-client, not per-DOI
            return None
        if status != 200:
            return None
        pdf_url = self._extract_pdf_url(html, base)
        if not pdf_url:
            return None
        status2, body2, headers2 = self._get(pdf_url)
        ctype2 = headers2.get("content-type", "").lower()
        return body2 if self._is_pdf(status2, ctype2, body2) else None

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        if not self._enabled:
            return failed("scidb provider is opt-in (enable_pdf_download: false)", self.name)
        cached = self._cache_path(doi)
        if cached.exists():
            data = cached.read_bytes()
            return ok(
                {"doi": doi, "pdf_path": str(cached),
                 "sha256": hashlib.sha256(data).hexdigest(),
                 "size_bytes": len(data), "cached": True},
                self.name,
            )
        live = self._live_mirrors()
        if not live:
            if self._blocked:
                return failed(_COOKIE_HELP, self.name)
            return failed("scidb: all mirrors unreachable", self.name)
        for base in live:
            data = self._try_mirror(base, doi)
            if data is not None:
                return self._ok_pdf(doi, cached, data, base)
        if self._blocked and not self._live_mirrors():
            return failed(_COOKIE_HELP, self.name)
        return failed(f"scidb: no pdf found for {doi}", self.name)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("scidb is DOI-only; arXiv PDFs are open at arxiv.org", self.name)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        return failed("scidb does not support title search; use annas", self.name)
