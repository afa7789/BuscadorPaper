"""research_graph.ingestion.url — classify URLs as arxiv / doi / unknown.

Cheap classifier (no HTTP) used by ``ingestion.inputs.dispatch`` to decide
which sub-resolver to invoke. arXiv ids are normalized (strip .pdf, keep
version suffix like v2).
"""

from __future__ import annotations

import re
from typing import Literal

from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"doi\.org/(.+)$", re.IGNORECASE)


def classify(url: str) -> Literal["arxiv", "doi", "unknown"]:
    if not url:
        return "unknown"
    if _ARXIV_URL_RE.search(url):
        return "arxiv"
    if _DOI_URL_RE.search(url):
        return "doi"
    return "unknown"


def resolve(url: str, registry: ProviderRegistry) -> list[Paper]:
    kind = classify(url)
    if kind == "unknown":
        return []
    if kind == "arxiv":
        m = _ARXIV_URL_RE.search(url)
        if not m:
            return []
        arxiv_id = m.group(1)
        provider = registry.get("arxiv")
        if provider is None:
            return []
        r = provider.fetch_by_arxiv_id(arxiv_id)
        if r.status == "failed" or r.data is None:
            return []
        papers = r.data if isinstance(r.data, list) else [r.data]
        return [p for p in papers if isinstance(p, Paper)]
    # doi
    m = _DOI_URL_RE.search(url)
    if not m:
        return []
    doi = m.group(1).strip().lower()
    from research_graph.ingestion.doi import resolve_doi
    r = resolve_doi(doi, registry)
    if r.status == "failed" or r.data is None:
        return []
    papers = r.data if isinstance(r.data, list) else [r.data]
    return [p for p in papers if isinstance(p, Paper)]
