"""research_graph.ingestion.backfill — fill missing abstracts from other providers.

Why this exists
---------------
Crossref frequently returns works with **no** ``abstract`` field (Taylor &
Francis, Wiley and Sage often deposit only metadata). That is fatal twice
over:

1. The LLM extraction stage reads ``title + abstract``. With no abstract it
   has nothing to ground a limitation or future-work claim in, so the paper
   silently contributes nothing to the open-questions report.
2. ``expansion.ranking._relevance`` scores ``abstract`` token overlap as 0.0
   when either side is missing, so abstract-less papers are pushed to the
   bottom of every ranking — even when their titles are squarely on topic.

So we re-ask a provider that *does* carry abstracts (OpenAlex reconstructs
them from ``abstract_inverted_index``) for exactly those papers that lack one.

Only the ``abstract`` field is copied across. The original ``paper_id``,
``doi``, title and provenance stay as Crossref produced them, so downstream
graph edges and cache keys remain stable.
"""

from __future__ import annotations

import logging
from typing import Iterable

from research_graph.models import Paper
from research_graph.providers import ProviderRegistry

logger = logging.getLogger(__name__)

# Providers to try, in order, when backfilling an abstract. First one that
# yields a non-empty abstract wins.
_FILLER_PROVIDERS = ("openalex", "semantic_scholar")


def _needs_abstract(paper: Paper) -> bool:
    return not (paper.abstract or "").strip() and bool(paper.doi)


def backfill_abstracts(
    papers: Iterable[Paper],
    registry: ProviderRegistry,
    *,
    limit: int = 100,
) -> list[Paper]:
    """Return ``papers`` with missing abstracts filled where possible.

    ``limit`` caps the number of network calls so a large ingest cannot turn
    into an unbounded crawl. Returns the same Paper objects, mutated in place
    via ``model_copy`` on the ones that were filled; papers that cannot be
    filled are returned untouched.
    """
    fillers = [(name, registry.get(name)) for name in _FILLER_PROVIDERS]
    fillers = [(name, p) for name, p in fillers if p is not None and hasattr(p, "fetch_by_doi")]
    if not fillers:
        logger.warning("backfill: no abstract-capable provider registered; skipping")
        return list(papers)

    out: list[Paper] = []
    filled = 0
    attempted = 0
    for paper in papers:
        if not _needs_abstract(paper):
            out.append(paper)
            continue
        if attempted >= limit:
            out.append(paper)
            continue
        attempted += 1
        for _name, provider in fillers:
            try:
                r = provider.fetch_by_doi(paper.doi)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover - provider-specific
                logger.debug("backfill: %s failed for %s: %s", _name, paper.doi, exc)
                continue
            if r is None or r.status != "ok":
                continue
            abstract = (getattr(r.data, "abstract", None) or "").strip()
            if not abstract:
                continue
            out.append(
                paper.model_copy(
                    update={
                        "abstract": abstract,
                        "source_provenance": {
                            **(paper.source_provenance or {}),
                            f"abstract_from_{_name}": ["abstract"],
                        },
                    }
                )
            )
            filled += 1
            break
        else:
            out.append(paper)

    logger.info(
        "backfill: attempted %d, filled %d abstracts (%d still missing)",
        attempted,
        filled,
        sum(1 for p in out if not (p.abstract or "").strip()),
    )
    return out


__all__ = ["backfill_abstracts"]