"""research_graph.providers.ddg — DuckDuckGo web-search provider.

DuckDuckGo has a public HTML search endpoint at https://duckduckgo.com/html/
that returns real search results without any API key, authentication, or rate
limit (DDG deliberately allows scraping at moderate rates).

Used as a free, zero-config discovery layer when Tavily/Perplexity keys are
absent. Quality is lower than Tavily (no AI ranking, results are noisier),
but it always works and never rate-limits.

For DOI/arXiv extraction we use the same regexes as TavilyProvider.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from research_graph.config import Config
from research_graph.models import Paper
from research_graph.providers.base import (
    AcademicProvider,
    ProviderResult,
    failed,
    ok,
    partial,
)


_log = logging.getLogger(__name__)

_DDG_HTML_ENDPOINT = "https://duckduckgo.com/html/"
_DDG_LITE_ENDPOINT = "https://duckduckgo.com/lite/"

# DDG's result rows: <a class="result__a" href="...">title</a> with snippet below.
_RESULT_A_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_DOI_IN_URL_RE = re.compile(r"10\.\d{2,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_ID_IN_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{1,5}(?:v\d+)?)", re.IGNORECASE)


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub("", text)).strip()


def _decode_ddg_href(href: str) -> str:
    """DDG wraps real URLs in a redirect; unwrap it.

    DDG href looks like:
      //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath&...
    Real URL is in the `uddg` query param.
    """
    try:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    except Exception:
        pass
    return href


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


def _paper_from_ddg_result(title: str, url: str, snippet: str, idx: int) -> Paper:
    doi = _extract_doi_from_url(url)
    arxiv = _extract_arxiv_id_from_url(url)
    if doi:
        paper_id = f"doi:{doi}"
    elif arxiv:
        paper_id = f"arxiv:{arxiv}"
    else:
        paper_id = f"ddg:{idx}:{_host_from_url(url)}"
    return Paper(
        paper_id=paper_id,
        title=title,
        year=None,
        doi=doi,
        urls=[url] if url else [],
        authors=[],
        abstract=snippet[:1500] if snippet else None,
        venue=_host_from_url(url).replace("www.", ""),
        source_provenance={"duckduckgo": ["title", "url", "snippet"]},
    )


class DDGProvider(AcademicProvider):
    """DuckDuckGo HTML search — free, no key, no rate limit."""

    name = "ddg"

    def __init__(self, config: Config) -> None:
        self._client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
                ),
            },
        )
        # DDG does not impose a hard limit, but be polite.
        self._min_interval = 1.0
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _search_html(self, query: str, limit: int) -> ProviderResult:
        self._throttle()
        try:
            resp = self._client.post(
                _DDG_HTML_ENDPOINT,
                data={"q": query, "kl": "us-en"},
            )
        except Exception as e:
            return failed(f"ddg: {e}", self.name)
        if resp.status_code in (202, 403):
            # DDG sometimes returns 202 with a "challenge" page; retry lite.
            try:
                self._throttle()
                resp = self._client.post(
                    _DDG_LITE_ENDPOINT,
                    data={"q": query, "kl": "us-en"},
                )
            except Exception as e:
                return failed(f"ddg: {e}", self.name)
        if resp.status_code != 200:
            return failed(
                f"ddg HTTP {resp.status_code}",
                self.name,
                raw={"text": resp.text[:500]},
            )
        return ok({"html": resp.text}, self.name, raw={"html": resp.text[:5000]})

    def _parse(self, html: str) -> list[tuple[str, str, str]]:
        """Return list of (title, url, snippet)."""
        titles_urls = _RESULT_A_RE.findall(html)
        snippets = _RESULT_SNIPPET_RE.findall(html)
        out: list[tuple[str, str, str]] = []
        for i, (href, title) in enumerate(titles_urls):
            real_url = _decode_ddg_href(href)
            title_clean = _clean(title)
            if not title_clean or not real_url.startswith("http"):
                continue
            snip = _clean(snippets[i]) if i < len(snippets) else ""
            out.append((title_clean, real_url, snip))
        return out

    def search_by_title(self, title: str, limit: int = 10) -> ProviderResult:
        # Bias towards academic sites by including the same domain allowlist
        # we use elsewhere.
        query = (
            f'"{title}" site:arxiv.org OR site:eprint.iacr.org OR site:openreview.net '
            f'OR site:acm.org OR site:ieee.org OR site:springer.com OR site:dl.acm.org'
        )
        r = self._search_html(query, limit)
        if r.status != "ok" or not isinstance(r.data, dict):
            return failed(f"ddg search failed: {r.error}", self.name)
        parsed = self._parse(r.data.get("html", ""))
        papers = [_paper_from_ddg_result(t, u, s, i) for i, (t, u, s) in enumerate(parsed[:limit])]
        if not papers:
            return partial([], self.name, error="ddg returned no parseable results")
        return ok(papers, self.name, raw=r.data)

    def fetch_by_doi(self, doi: str) -> ProviderResult:
        return failed("ddg does not have DOI lookup", self.name)

    def fetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return failed("ddg does not have arxiv lookup", self.name)

    async def afetch_by_doi(self, doi: str) -> ProviderResult:
        return self.fetch_by_doi(doi)

    async def afetch_by_arxiv_id(self, arxiv_id: str) -> ProviderResult:
        return self.fetch_by_arxiv_id(arxiv_id)

    def get_references(self, paper_id: str) -> ProviderResult:
        return failed("ddg does not expose references", self.name)

    def get_citations(self, paper_id: str, limit: int = 50) -> ProviderResult:
        return failed("ddg does not expose citations", self.name)

    def get_author_works(self, author_id: str, limit: int = 25) -> ProviderResult:
        display = author_id.split(":", 1)[-1].replace("_", " ").replace("-", " ")
        query = (
            f'"{display}" site:arxiv.org OR site:openreview.net '
            f'OR site:acm.org OR site:eprint.iacr.org papers'
        )
        r = self._search_html(query, limit)
        if r.status != "ok" or not isinstance(r.data, dict):
            return failed(f"ddg author search failed: {r.error}", self.name)
        parsed = self._parse(r.data.get("html", ""))
        papers = [_paper_from_ddg_result(t, u, s, i)
                  for i, (t, u, s) in enumerate(parsed[:limit])]
        return ok(papers, self.name, raw=r.data)
