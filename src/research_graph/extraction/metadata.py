"""research_graph.extraction.metadata — declared metadata extraction (no LLM).

The whole point of this module is to produce a baseline ``ExtractionRecord``
from the bibliographic ``Paper`` object alone — no model call, no network,
no heuristic. The "Declared vs Inferred" axis on every downstream claim
depends on having this guaranteed declared baseline so a paper that the
LLM stage failed on is still represented in the report.

Pure function on Paper; side-effect free.
"""

from __future__ import annotations

import re

from research_graph.models import ExtractionRecord, Paper


# ---------- arXiv ID extraction from Paper.urls -------------------------------

_ARXIV_URL_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)


def _arxiv_id_from_urls(urls: list[str]) -> str | None:
    for url in urls:
        m = _ARXIV_URL_RE.search(url)
        if m:
            return m.group(1)
    return None


# ---------- Public API --------------------------------------------------------

def extract_declared(paper: Paper) -> dict:
    """Pull the declared bibliographic fields out of a Paper record.

    Returns a dict with the following keys (all from Paper, never from
    any external lookup):

      - paper_id      (str)
      - year          (int | None)
      - doi           (str | None)
      - arxiv_id      (str | None) — mined from Paper.urls
      - authors       (list[str])
      - venue         (str | None)
      - citation_count (int | None) — only present if a provider set it
      - keywords      (list[str])

    No LLM, no network, no heuristics beyond the arXiv URL regex. Missing
    fields are returned as ``None`` / empty list so the caller can rely on
    the shape.
    """
    # ``Paper`` has no dedicated ``citation_count`` field, but providers
    # sometimes stash it under ``source_provenance`` (it isn't in the
    # schema). We surface whatever exists there for downstream consumers
    # that know how to interpret it, and leave it None otherwise.
    citation_count: int | None = None
    cc_raw = paper.source_provenance.get("citation_count")  # type: ignore[arg-type]
    if cc_raw:
        try:
            citation_count = int(cc_raw[0])
        except (ValueError, TypeError):
            citation_count = None

    return {
        "paper_id": paper.paper_id,
        "year": paper.year,
        "doi": paper.doi,
        "arxiv_id": _arxiv_id_from_urls(paper.urls),
        "authors": list(paper.authors),
        "venue": paper.venue,
        "citation_count": citation_count,
        "keywords": [],  # Paper has no keyword field; reserved for future
    }


def _declared_confidence(paper: Paper) -> float:
    """Confidence scale: 1.0 (full metadata), 0.5 (title only), 0.0 (none)."""
    has_title = bool(paper.title and paper.title.strip())
    has_year = paper.year is not None
    has_doi = bool(paper.doi)
    if has_title and has_year and has_doi:
        return 1.0
    if has_title:
        return 0.5
    return 0.0


def declared_to_extraction_record(paper: Paper) -> ExtractionRecord:
    """Build a minimal ExtractionRecord straight from a Paper — no LLM.

    The returned record carries only what the Paper record explicitly
    declares; claims / limitations / future-work lists are empty by
    construction (the LLM stage is responsible for filling them).

    ``extraction_confidence`` encodes how much of the declared baseline
    we actually have:
      - 1.0  — title + year + doi all present
      - 0.5  — title only (year or doi missing)
      - 0.0  — no title at all
    """
    declared = extract_declared(paper)
    confidence = _declared_confidence(paper)

    # ExtractionRecord requires non-empty ``problem`` and ``main_contribution``
    # strings. For a metadata-only pass we don't have those yet, so we
    # surface placeholders that downstream stages can detect and replace.
    # The placeholder is intentionally bland so a malformed "metadata-only"
    # record is easy to spot in the report.
    problem = paper.title or ""
    main_contribution = ""

    return ExtractionRecord(
        paper_id=paper.paper_id,
        problem=problem,
        main_contribution=main_contribution,
        extraction_confidence=confidence,
        # All claim/limitation/future-work/open-problem lists are empty:
        # this record is the declared baseline, nothing has been inferred.
        research_area=[],
        technical_components=[],
        baseline_or_replaced_technique=[],
        proposed_technique=[],
        application_domain=[],
        security_properties=[],
        evaluation_metrics=[],
        datasets_or_experimental_setup=[],
        limitations=[],
        future_work=[],
        open_questions=[],
        claims_with_evidence=[],
    )