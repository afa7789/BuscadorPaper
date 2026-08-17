"""research_graph.ingestion.title — title-based search across providers.

Stops early when a provider returns enough hits AND the top result has a
DOI (high-confidence match). Falls back to the next provider otherwise.
"""

from __future__ import annotations

from research_graph.ingestion.dedup import merge
from research_graph.models import Paper
from research_graph.providers import ProviderRegistry


def search_title(title: str, registry: ProviderRegistry, limit: int = 5) -> list[Paper]:
    collected: list[Paper] = []
    for provider in registry.all():
        if not hasattr(provider, "search_by_title"):
            continue
        r = provider.search_by_title(title, limit=limit)
        if r.status == "failed" or r.data is None:
            continue
        papers = r.data if isinstance(r.data, list) else [r.data]
        collected.extend(p for p in papers if isinstance(p, Paper))
        # Stop early if first provider gave enough results with DOI
        if len(collected) >= limit and collected[0].doi:
            break
    return merge(collected)[:limit]


def search_pdf_title_guess(pdf_extract) -> str | None:
    """Heuristic: take the first non-empty line of page 1, validate shape."""
    if not pdf_extract or not pdf_extract.page_texts:
        return None
    first = pdf_extract.page_texts[0].strip()
    for line in first.splitlines():
        line = line.strip()
        if 5 <= len(line) <= 200 and not line.endswith(".") and not line.isupper():
            return line
    return None
