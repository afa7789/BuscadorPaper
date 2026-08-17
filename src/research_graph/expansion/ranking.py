"""research_graph.expansion.ranking — score and rank candidate papers.

Scoring (each in [0, 1]):
    recency_score   = max(0, 1 - (current_year - candidate.year) / 10)
    relevance_score = combination of:
        - title token overlap (binary 0/0.5/1.0)
        - abstract token overlap (binary 0/0.5/1.0, normalized)
        - shared affiliation / shared venue (small bonus)
    citation_score  = min(1.0, log10(1 + citation_count or 0) / 3)

    final = 0.35 * recency + 0.45 * relevance + 0.20 * citation

Why title + abstract: paper titles alone don't carry enough signal across
seed sets; abstract token overlap (top-N tokens, Jaccard) gives a much
better signal that a paper belongs to the same area without requiring
a dedicated concepts field on the Paper model.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache

from research_graph.models import Paper


_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "with",
    "to", "by", "from", "is", "are", "be", "this", "that", "these",
    "those", "as", "at", "it", "its", "we", "our", "their", "a", "i",
    "ii", "iii", "iv",
}


def _tokens(text: str, *, top_n: int | None = None) -> set[str]:
    text = (text or "").lower()
    words = re.findall(r"[a-z][a-z\-]+", text)
    out = {w for w in words if len(w) >= 3 and w not in _STOPWORDS}
    if top_n is not None and len(out) > top_n:
        # Keep the top_n most "informative" by length (longer words = more specific).
        out = set(sorted(out, key=lambda w: -len(w))[:top_n])
    return out


def _default_clock() -> int:
    """Return the current year.

    Override via env var ``RESEARCH_GRAPH_CLOCK_ISO=YYYY-MM-DDTHH:MM:SS``
    or by passing a callable as the ``clock`` kwarg to ``score``/``rank``.
    Useful for deterministic snapshot tests and CI runs.
    """
    override = os.environ.get("RESEARCH_GRAPH_CLOCK_ISO")
    if override:
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(override).year
        except ValueError:
            pass
    from datetime import datetime as _dt
    return _dt.now().year


def _recency(paper: Paper, *, clock=_default_clock) -> float:
    if paper.year is None:
        return 0.3
    current_year = clock()
    return max(0.0, 1.0 - (current_year - paper.year) / 10.0)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _relevance(seed: Paper, candidate: Paper) -> float:
    """Combine title overlap, abstract overlap, and shared venue signals."""
    # Title overlap: small bag, so use raw overlap count to a score
    seed_title = _tokens(seed.title or "", top_n=8)
    cand_title = _tokens(candidate.title or "", top_n=8)
    title_score = _jaccard(seed_title, cand_title)
    # Abstract overlap: larger bag, Jaccard is meaningful
    seed_abs = _tokens(seed.abstract or "", top_n=40)
    cand_abs = _tokens(candidate.abstract or "", top_n=40)
    abs_score = _jaccard(seed_abs, cand_abs)
    # Venue/affiliation shared: small bonus
    shared_venue = 0.0
    if seed.venue and candidate.venue and seed.venue.lower() == candidate.venue.lower():
        shared_venue = 0.1
    # Combine (each in [0,1])
    combined = 0.4 * title_score + 0.5 * abs_score + shared_venue
    return min(1.0, combined)


def _citation(paper: Paper) -> float:
    count = getattr(paper, "citation_count", None)
    if count is None:
        return 0.1
    return min(1.0, math.log10(1 + count) / 3.0)


def score(seed: Paper, candidate: Paper, *, clock: Callable[[], int] | None = None) -> float:
    return (
        0.35 * _recency(candidate, clock=clock or _default_clock)
        + 0.45 * _relevance(seed, candidate)
        + 0.20 * _citation(candidate)
    )


def rank(
    candidates: list[Paper],
    seeds: list[Paper],
    *,
    min_score: float = 0.35,
    clock: Callable[[], int] | None = None,
) -> list[Paper]:
    """Score each candidate against the best seed; return >= min_score sorted desc.

    Sort key is ``(-score, paper_id)`` so ties are broken deterministically
    by paper_id — reruns produce byte-identical output for byte-identical input.
    """
    if not seeds:
        return sorted(
            (c for c in candidates if _recency(c, clock=clock or _default_clock) >= min_score),
            key=lambda c: (-_recency(c, clock=clock or _default_clock), c.paper_id or ""),
        )
    scored: list[tuple[float, Paper]] = []
    clk = clock or _default_clock
    for c in candidates:
        best = max(score(s, c, clock=clk) for s in seeds)
        if best >= min_score:
            scored.append((best, c))
    # Deterministic tie-break: paper_id ascending when scores tie.
    scored.sort(key=lambda t: (-t[0], t[1].paper_id or ""))
    return [p for _, p in scored]
