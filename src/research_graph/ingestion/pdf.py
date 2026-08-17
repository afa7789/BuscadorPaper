"""research_graph.ingestion.pdf — extract text + heuristic reference parsing.

Heavy lifting uses ``pypdf``. We never raise out of this module for a
broken PDF (encrypted, scanned, zero-page): we return an empty
``PDFExtract`` and log a warning so the ingest pipeline can decide to
skip. File-not-found IS propagated because the caller (CLI / orchestrator)
is responsible for resolving inputs.

The DOI / arXiv regexes here are deliberately permissive — they bias
toward over-matching so the downstream dedup stage has more to work with.
False positives are cheap; missing a real DOI is expensive.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)


# ---------- Result type -------------------------------------------------------

@dataclass
class PDFExtract:
    full_text: str = ""
    page_texts: list[str] = field(default_factory=list)
    references_section: str = ""
    parsed_references: list[str] = field(default_factory=list)
    doi_guess: str | None = None
    arxiv_guess: str | None = None


# ---------- Regexes -----------------------------------------------------------

# Headings that mark the start of a references/bibliography block.
_REFERENCES_HEADING_RE = re.compile(
    r"^\s*(references|bibliography|works\s+cited|literature\s+cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Permissive DOI matcher. DOI handbook allows a wide character set; we
# keep the common shape and let dedup filter later.
_DOI_RE = re.compile(
    r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
    re.IGNORECASE,
)

# Strip trailing punctuation that's almost never part of a real DOI.
_DOI_TRAILING_PUNCT = ".,)]}»”’\""

# arXiv ID with the literal "arXiv:" prefix (preferred when present).
_ARXIV_PREFIXED_RE = re.compile(
    r"arXiv:\s?(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)

# Bare arXiv ID — only trusted when we already saw an arXiv mention, so
# we don't accidentally treat any 4.4-digit number as one. We compute the
# bare-ID list separately and tag it that way.
_ARXIV_BARE_RE = re.compile(
    r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b"
)


# ---------- Public API --------------------------------------------------------

def _empty_extract() -> PDFExtract:
    return PDFExtract()


def _strip_doi_tail(s: str) -> str:
    return s.rstrip(_DOI_TRAILING_PUNCT)


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    """De-duplicate while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _find_references_section(full_text: str) -> str:
    """Return the substring after the first References/Bibliography heading.

    If no heading is found, returns "". The references section runs to end
    of the document because academic papers never have meaningful content
    after the bibliography.
    """
    m = _REFERENCES_HEADING_RE.search(full_text)
    if not m:
        return ""
    return full_text[m.end():]


def _scan_doi(text: str) -> str | None:
    """First DOI match in the text, with trailing punctuation trimmed."""
    m = _DOI_RE.search(text)
    if not m:
        return None
    return _strip_doi_tail(m.group(0))


def _scan_arxiv(text: str) -> str | None:
    """First arXiv ID match — prefer the explicit "arXiv:" form, fall back
    to a bare ID if we already saw an "arXiv:" mention anywhere in the doc.
    """
    m = _ARXIV_PREFIXED_RE.search(text)
    if m:
        return m.group(1)
    if re.search(r"arXiv", text, re.IGNORECASE):
        m = _ARXIV_BARE_RE.search(text)
        if m:
            return m.group(1)
    return None


def _parse_references(refs_text: str) -> list[str]:
    """Split the references section into candidate reference strings.

    Heuristic: split on blank lines (most bibliographies use blank lines
    between entries). Within each block, also try splitting on numbered
    markers like ``[1]`` or ``1.`` at the start of a line.
    """
    if not refs_text.strip():
        return []

    # Normalize Windows line endings, then split on blank lines.
    refs_text = refs_text.replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = re.split(r"\n\s*\n", refs_text)

    # Secondary split: numbered markers within blocks.
    pieces: list[str] = []
    for block in raw_blocks:
        sub = re.split(
            r"\n(?=\s*(?:\[\d+\]|\d+\.|\d+\)\s))",
            block,
        )
        for s in sub:
            s = s.strip()
            if s:
                pieces.append(s)

    # As a safety net, also accept the whole section as one entry — it's
    # better than dropping it entirely if the heuristic misses a format.
    if not pieces and refs_text.strip():
        pieces = [refs_text.strip()]

    return _dedupe_preserve_order(pieces)


def extract_text_and_refs(path: str | Path) -> PDFExtract:
    """Extract text + heuristic DOI/arXiv from a single PDF file.

    Robust against:
      - encrypted PDFs (warning + empty)
      - scanned PDFs with no extractable text (empty text, no crash)
      - malformed PDFs (warning + empty)

    Raises:
      FileNotFoundError: if ``path`` does not exist (callers handle).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {p}")

    try:
        reader = PdfReader(str(p))
    except (PdfReadError, OSError, ValueError) as exc:
        logger.warning("PDF open failed for %s: %s", p, exc)
        return _empty_extract()

    # Some encrypted PDFs raise on page iteration rather than on construction.
    try:
        page_texts: list[str] = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except (PdfReadError, Exception) as exc:  # pypdf raises broad
                logger.warning("PDF page extract failed in %s: %s", p, exc)
                txt = ""
            page_texts.append(txt)
    except (PdfReadError, Exception) as exc:  # encrypted PDFs etc.
        logger.warning("PDF iteration failed for %s: %s", p, exc)
        return _empty_extract()

    full_text = "\n".join(page_texts)
    references_section = _find_references_section(full_text)
    parsed_references = _parse_references(references_section)

    doi_guess = _scan_doi(full_text)
    arxiv_guess = _scan_arxiv(full_text)

    return PDFExtract(
        full_text=full_text,
        page_texts=page_texts,
        references_section=references_section,
        parsed_references=parsed_references,
        doi_guess=doi_guess,
        arxiv_guess=arxiv_guess,
    )