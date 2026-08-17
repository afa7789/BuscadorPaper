"""research_graph.analysis.limitations — group similar limitations + future work."""

from __future__ import annotations

import re
import string
from typing import Iterable

from research_graph.models import ExtractionRecord


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return set(text.split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _bucket(texts: Iterable[str], threshold: float = 0.4) -> dict[str, list[str]]:
    buckets: list[tuple[set[str], list[str]]] = []
    for t in texts:
        toks = _tokens(t)
        placed = False
        for rep_toks, members in buckets:
            if _jaccard(toks, rep_toks) >= threshold:
                members.append(t)
                placed = True
                break
        if not placed:
            buckets.append((toks, [t]))
    return {f"bucket_{i}": members for i, (_, members) in enumerate(buckets)}


def group(records: list[ExtractionRecord]) -> dict:
    """Bucket limitations and future-work by token Jaccard (>= 0.4)."""
    lim_texts = [lim.text for r in records for lim in (r.limitations or [])]
    fw_texts = [fw.text for r in records for fw in (r.future_work or [])]
    return {
        "limitations": _bucket(lim_texts),
        "future_work": _bucket(fw_texts),
    }
