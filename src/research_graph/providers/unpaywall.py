"""research_graph.providers.unpaywall — legal open-access PDF fetcher by DOI.

Unpaywall (unpaywall.org) is a free, legal index of OA locations for
~50M DOIs, maintained by OurResearch. One GET per DOI, no key needed —
only a contact email (reuses OPENALEX_EMAIL / CROSSREF_MAILTO).

Opt-in like the other download providers:
    outputs.enable_pdf_download: true
    "unpaywall" in outputs.pdf_download_providers
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import httpx

from research_graph.config import Config
from research_graph.providers.base import AcademicProvider, ProviderResult, failed, ok


_log = logging.getLogger(__name__)

_API = "https://api.unpaywall.org/v2/{doi}"


def _contact_email() -> str | None:
    for var in ("UNPAYWALL_EMAIL", "OPENALEX_EMAIL", "CROSSREF_MAILTO"):
        v = os.environ.get(var, "").strip()
        if v:
            return v
    return None


class UnpaywallProvider(AcademicProvider):
    """Fetch full-text PDFs from legal OA locations resolved by DOI."""

    name = "unpaywall"

    def __init__(self, config: Config, cache_dir: Path | None = None) -> None:
        if cache_dir is None:
            cache_dir = Path(getattr(config.project, "cache_dir", "./cache")) / "unpaywall"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(timeout=60.0, follow_redirects=True)
        self._email = _contact_email()
        self._min_interval = 1.0
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

    def _cache_path(self, doi: str) -> Path:
        h = hashlib.sha256(doi.lower().encode()).hexdigest()[:16]
        return self._cache_dir / f"{h}.pdf"

    def _pdf_urls(self, record: dict) -> list[str]:
        urls: list[str] = []
        best = record.get("best_oa_location") or {}
        if best.get("url_for_pdf"):
            urls.append(best["url_for_pdf"])
        for loc in record.get("oa_locations") or []:
            u = (loc or {}).get("url_for_pdf")
            if u and u not in urls:
                urls.append(u)
        return urls

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        if not self._enabled:
            return failed("unpaywall provider is opt-in (enable_pdf_download: false)", self.name)
        if not self._email:
            return failed(
                "unpaywall needs a contact email; set OPENALEX_EMAIL or UNPAYWALL_EMAIL in .env",
                self.name,
            )
        cached = self._cache_path(doi)
        if cached.exists():
            data = cached.read_bytes()
            return ok(
                {"doi": doi, "pdf_path": str(cached),
                 "sha256": hashlib.sha256(data).hexdigest(),
                 "size_bytes": len(data), "cached": True},
                self.name,
            )
        self._throttle()
        try:
            resp = self._client.get(_API.format(doi=doi), params={"email": self._email})
        except Exception as e:
            return failed(f"unpaywall API error: {e}", self.name)
        if resp.status_code != 200:
            return failed(f"unpaywall HTTP {resp.status_code} for {doi}", self.name)
        try:
            record = resp.json()
        except Exception as e:
            return failed(f"unpaywall bad JSON: {e}", self.name)
        urls = self._pdf_urls(record)
        if not urls:
            return failed(f"unpaywall: no OA pdf location for {doi}", self.name)
        for url in urls[:3]:
            content = self._download_pdf(url)
            if content is None:
                continue
            cached.write_bytes(content)
            return ok(
                {"doi": doi, "pdf_path": str(cached),
                 "sha256": hashlib.sha256(content).hexdigest(),
                 "size_bytes": len(content), "cached": False, "url": url},
                self.name,
            )
        return failed(f"unpaywall: OA locations for {doi} did not yield a PDF", self.name)

    def _download_pdf(self, url: str) -> bytes | None:
        self._throttle()
        try:
            r = self._client.get(url)
        except Exception:
            return None
        ctype = r.headers.get("content-type", "").lower()
        if r.status_code != 200 or len(r.content) < 1024:
            return None
        if "pdf" not in ctype and "octet-stream" not in ctype:
            return None
        return r.content

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("unpaywall is DOI-only", self.name)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def search_by_title(self, title: str, limit: int = 5) -> ProviderResult:
        return failed("unpaywall does not support title search", self.name)
