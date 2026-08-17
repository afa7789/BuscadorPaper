"""research_graph.ingestion.dedup — merge multiple Paper records for the same work.

Key precedence (first match wins):
  1. DOI
  2. arXiv id (in paper_id)
  3. S2 id (paper_id starts with "s2:" or matches the SHA-40 pattern)
  4. OpenAlex id (paper_id starts with "openalex:" or matches ^W\\d+$)
  5. Fallback: normalized_title|first_author_family_lower|year

When merging, first occurrence's paper_id wins; other fields take the
non-null value preferring earlier occurrences; authors/concepts are unioned.
"""

from __future__ import annotations

from typing import Iterable

from research_graph.models import Paper
from research_graph.ingestion.normalize import paper_dedup_key


_S2_ID_RE = __import__("re").compile(r"^[0-9a-f]{40}$", __import__("re").IGNORECASE)
_OA_ID_RE = __import__("re").compile(r"^W\d+$")


def dedup_key(paper: Paper) -> str:
    """Delegate to normalize.paper_dedup_key."""
    return paper_dedup_key(paper)


def merge(papers: Iterable[Paper]) -> list[Paper]:
    """Merge multiple Paper records by canonical key. Returns one Paper per key."""
    by_key: dict[str, Paper] = {}
    first_seen: dict[str, Paper] = {}
    for paper in papers:
        k = paper_dedup_key(paper)
        if k not in by_key:
            by_key[k] = paper
            first_seen[k] = paper
            continue
        by_key[k] = _merge_pair(first_seen[k], paper)
    return list(by_key.values())


def _merge_pair(older: Paper, newer: Paper) -> Paper:
    """Field-by-field merge: prefer older non-null values; union lists."""
    data = older.model_dump()
    new = newer.model_dump()
    # Single-value fields: keep older non-null
    for f in ("year", "doi", "abstract", "venue"):
        if data.get(f) in (None, "") and new.get(f) not in (None, ""):
            data[f] = new[f]
    # Lists: union (de-dup by string)
    for f in ("authors", "urls"):
        seen = list(data.get(f) or [])
        for v in new.get(f) or []:
            if v not in seen:
                seen.append(v)
        data[f] = seen
    # source_provenance: merge
    sp = dict(data.get("source_provenance") or {})
    for k, vs in (new.get("source_provenance") or {}).items():
        sp[k] = list({*sp.get(k, []), *vs})
    data["source_provenance"] = sp
    return Paper.model_validate(data)
