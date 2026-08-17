"""research_graph.providers.fallback — convenience helpers around Resolver.

The Resolver itself lives in ``research_graph.providers.__init__`` because
the registry needs to be importable without circular imports. This module
adds higher-level helpers used by ingestion and expansion stages.
"""

from __future__ import annotations

from research_graph.models import Paper, ProviderResult
from research_graph.providers import ProviderRegistry, Resolver


def resolve_doi(doi: str, registry: ProviderRegistry) -> ProviderResult:
    """Walk providers in priority order looking up a DOI."""
    resolver = Resolver(registry)
    return resolver.resolve(lambda p: p.fetch_by_doi(doi))


def resolve_arxiv(arxiv_id: str, registry: ProviderRegistry) -> ProviderResult:
    resolver = Resolver(registry)
    return resolver.resolve(lambda p: p.fetch_by_arxiv_id(arxiv_id))


def search_title(title: str, registry: ProviderRegistry, limit: int = 5) -> list[Paper]:
    """Try each provider's title search; dedup via the first occurrence of each paper_id."""
    resolver = Resolver(registry)
    seen: dict[str, Paper] = {}
    for provider in registry.all():
        r = provider.search_by_title(title, limit=limit)
        if r.status == "failed" or r.data is None:
            continue
        papers = r.data if isinstance(r.data, list) else [r.data]
        for p in papers:
            if p.paper_id and p.paper_id not in seen:
                seen[p.paper_id] = p
        if len(seen) >= limit:
            break
    return list(seen.values())[:limit]
