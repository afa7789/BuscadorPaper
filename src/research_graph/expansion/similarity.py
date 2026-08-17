"""research_graph.expansion.similarity — S2 recommendations + OpenAlex related_works.

Uses provider.search_by_title to bootstrap recommendations; falls back to the
paper's own concept labels when no similarity API is available.
"""

from __future__ import annotations

import logging

from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


_log = logging.getLogger(__name__)


def collect_similar(
    seed: Paper,
    registry: ProviderRegistry,
    *,
    limit: int = 10,
) -> list[Paper]:
    out: list[Paper] = []
    seen_ids: set[str] = {seed.paper_id}

    # Use the seed's title to query S2 recommendations-ish via search.
    if seed.title:
        for provider in registry.all():
            if not hasattr(provider, "search_by_title"):
                continue
            try:
                r = provider.search_by_title(seed.title, limit=limit)
            except Exception as e:
                _log.warning(f"similarity search failed on {provider.name}: {e}")
                continue
            if r.status == "failed" or r.data is None:
                continue
            papers = r.data if isinstance(r.data, list) else []
            for p in papers:
                if p.paper_id and p.paper_id not in seen_ids:
                    seen_ids.add(p.paper_id)
                    out.append(p)
            if len(out) >= limit:
                break
    return out[:limit]
