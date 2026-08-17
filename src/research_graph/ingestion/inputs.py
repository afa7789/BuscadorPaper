"""research_graph.ingestion.inputs — dispatch SeedInput entries to resolvers.

Single public function: ``dispatch(entry, registry) -> list[Paper]``.
Never raises; failures log a warning and return [].
"""

from __future__ import annotations

import logging

from research_graph.config import SeedInput
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


_log = logging.getLogger(__name__)


def dispatch(entry: SeedInput, registry: ProviderRegistry) -> list[Paper]:
    try:
        return _dispatch_inner(entry, registry)
    except Exception as e:
        _log.warning(f"ingestion.dispatch failed for {entry.type}:{entry.value[:80]}: {e}")
        return []


def _dispatch_inner(entry: SeedInput, registry: ProviderRegistry) -> list[Paper]:
    if entry.type == "doi":
        from research_graph.ingestion.doi import parse_doi, resolve_doi
        doi = parse_doi(entry.value)
        if not doi:
            return []
        r = resolve_doi(doi, registry)
        if r.status == "failed" or r.data is None:
            return []
        papers = r.data if isinstance(r.data, list) else [r.data]
        return [p for p in papers if isinstance(p, Paper)]

    if entry.type == "arxiv":
        provider = registry.get("arxiv")
        if provider is None:
            return []
        r = provider.fetch_by_arxiv_id(entry.value)
        if r.status == "failed" or r.data is None:
            return []
        papers = r.data if isinstance(r.data, list) else [r.data]
        return [p for p in papers if isinstance(p, Paper)]

    if entry.type == "title":
        from research_graph.ingestion.title import search_title
        return search_title(entry.value, registry, limit=5)[:3]

    if entry.type == "url":
        from research_graph.ingestion.url import resolve
        return resolve(entry.value, registry)

    if entry.type == "tavily_query":
        # Tavily web search as a discovery layer. Returns the top-N paper-like
        # results from Tavily directly. Use this in seed_inputs to bootstrap
        # the project when you don't have specific DOIs/URLs yet.
        tavily = registry.get("tavily")
        if tavily is None:
            _log.warning("tavily_query seed given but tavily provider not registered "
                         "(missing TAVILY_API_KEY?)")
            return []
        r = tavily.search_by_title(entry.value, limit=20)
        if r.status == "failed" or not isinstance(r.data, list):
            _log.warning(f"tavily_query failed for {entry.value!r}: {r.error}")
            return []
        return [p for p in r.data if isinstance(p, Paper)]

    if entry.type == "ddg_query":
        # DuckDuckGo web search fallback when Tavily isn't available. Same
        # shape as tavily_query: free, no key, returns ~10-20 paper-like
        # results. Quality is lower than Tavily but the system always works.
        ddg = registry.get("ddg")
        if ddg is None:
            _log.warning("ddg_query seed given but ddg provider not registered")
            return []
        r = ddg.search_by_title(entry.value, limit=20)
        if r.status == "failed" or not isinstance(r.data, list):
            _log.warning(f"ddg_query failed for {entry.value!r}: {r.error}")
            return []
        return [p for p in r.data if isinstance(p, Paper)]

    if entry.type == "crossref_query":
        # Crossref bibliographic search — works without any key, ~140M DOIs.
        # Returns up to ``limit`` works matching title+author+year+subject.
        cr = registry.get("crossref")
        if cr is None:
            _log.warning("crossref_query seed given but crossref provider not registered")
            return []
        r = cr.search_by_query(entry.value, limit=20)
        if r.status == "failed" or not isinstance(r.data, list):
            _log.warning(f"crossref_query failed for {entry.value!r}: {r.error}")
            return []
        return [p for p in r.data if isinstance(p, Paper)]

    if entry.type == "pdf":
        from pathlib import Path
        from research_graph.ingestion.pdf import extract_text_and_refs
        from research_graph.ingestion.doi import extract_doi_from_text, resolve_doi
        from research_graph.ingestion.title import search_pdf_title_guess, search_title
        path = Path(entry.value)
        if not path.exists():
            _log.warning(f"PDF not found: {path}")
            return []
        ex = extract_text_and_refs(path)
        doi = extract_doi_from_text(ex.full_text)
        if doi:
            r = resolve_doi(doi, registry)
            if r.status == "ok" and r.data is not None:
                papers = r.data if isinstance(r.data, list) else [r.data]
                return [p for p in papers if isinstance(p, Paper)]
        # Fallback to title search
        guess = search_pdf_title_guess(ex)
        if guess:
            return search_title(guess, registry, limit=3)
        return []

    _log.warning(f"unknown seed_input.type: {entry.type!r}")
    return []
