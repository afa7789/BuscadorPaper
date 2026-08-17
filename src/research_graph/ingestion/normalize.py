"""research_graph.ingestion.normalize — string normalization + dedup keys.

Pure stdlib helpers. No I/O, no network. Each function is deterministic so
the same input always produces the same dedup key — this is the contract
that lets the dedup stage merge records from different providers.

Dedup precedence (per paper):
    DOI > arXiv ID (from urls) > S2 ID (from urls) > OpenAlex ID (from urls)
    > (normalized_title, first_author_family_lower, year_or_unknown)

Authors and institutions follow the same precedence-first pattern.
"""

from __future__ import annotations

import re
import unicodedata

from research_graph.models import Author, Institution, Paper


# ---------- Internal helpers --------------------------------------------------

# A "year or unknown" sentinel used inside the title-based dedup key so two
# papers with missing years still collide instead of falling back to "".
_UNKNOWN_YEAR = "unknown"

# Surrounding-quote characters we strip from a title.
_QUOTE_CHARS = "\"'‘’“”"

# Common arXiv URL shapes — only used to mine the ID out of Paper.urls.
_ARXIV_URL_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)

# Semantic Scholar paper URL: semanticscholar.org/paper/<hash>
_S2_URL_RE = re.compile(
    r"semanticscholar\.org/paper/([0-9a-fA-F]{40})",
    re.IGNORECASE,
)

# OpenAlex work URL: openalex.org/W<id>  (the W-prefix is canonical).
_OPENALEX_URL_RE = re.compile(
    r"openalex\.org/(W\d+)", re.IGNORECASE
)


def _nfcs(s: str) -> str:
    """Unicode NFC normalize — guarantees decomposed/composed forms collide."""
    return unicodedata.normalize("NFC", s)


def _collapse_ws(s: str) -> str:
    """Collapse all whitespace runs to a single space, then strip ends."""
    return re.sub(r"\s+", " ", s).strip()


def _strip_trailing_period(s: str) -> str:
    """Drop a single trailing '.' — bibliographic titles rarely end in one."""
    if s.endswith("."):
        return s[:-1].rstrip()
    return s


def _strip_surrounding_quotes(s: str) -> str:
    """Strip matched pairs of surrounding quote characters."""
    if len(s) >= 2 and s[0] in _QUOTE_CHARS and s[-1] in _QUOTE_CHARS:
        return s[1:-1].strip()
    return s


def _arxiv_id_from_urls(urls: list[str]) -> str | None:
    for url in urls:
        m = _ARXIV_URL_RE.search(url)
        if m:
            return m.group(1)
    return None


def _s2_id_from_urls(urls: list[str]) -> str | None:
    for url in urls:
        m = _S2_URL_RE.search(url)
        if m:
            return m.group(1).lower()
    return None


def _openalex_id_from_urls(urls: list[str]) -> str | None:
    for url in urls:
        m = _OPENALEX_URL_RE.search(url)
        if m:
            return m.group(1).upper()
    return None


# ---------- Public API --------------------------------------------------------

def normalize_title(title: str) -> str:
    """NFC, lowercase, collapse whitespace, strip surrounding quotes, drop
    trailing period. Empty in -> empty out (no crash on missing data)."""
    if not title:
        return ""
    s = _nfcs(title)
    s = _collapse_ws(s)
    s = _strip_surrounding_quotes(s)
    s = s.lower()
    s = _strip_trailing_period(s)
    return s


def normalize_author_name(family: str, given: str | None = None) -> str:
    """NFC + lower + collapse-ws + strip on both parts; join with '|'.

    A None ``given`` becomes "-" so two records with missing given names
    still collide on the same key.
    """
    fam = _nfcs(family or "").lower()
    fam = _collapse_ws(fam)
    giv = _nfcs(given or "").lower() if given else "-"
    giv = _collapse_ws(giv)
    return f"{fam}|{giv}"


def paper_dedup_key(paper: Paper) -> str:
    """Build the canonical dedup key for a Paper.

    Precedence: DOI > arXiv ID > S2 ID > OpenAlex ID > normalized title key.
    The title branch is `(normalized_title, first_author_family_lower,
    year_or_unknown)` joined with '|'.
    """
    if paper.doi:
        return paper.doi.lower()

    arxiv = _arxiv_id_from_urls(paper.urls)
    if arxiv:
        return f"arxiv:{arxiv}"

    s2 = _s2_id_from_urls(paper.urls)
    if s2:
        return f"s2:{s2}"

    oa = _openalex_id_from_urls(paper.urls)
    if oa:
        return f"openalex:{oa}"

    first_author_family = ""
    if paper.authors:
        # ``Paper.authors`` is a list of display strings. We need a rough
        # family-name fallback for the title branch of the dedup key. The
        # two common bibliographic conventions are "Family, Given" and
        # "Given Family"; in both cases the family name is the token
        # following the last comma or, failing that, the last whitespace-
        # separated token. Lowercase so case differences don't split keys.
        first = paper.authors[0]
        if "," in first:
            first_author_family = first.split(",")[0]
        else:
            parts = first.split()
            first_author_family = parts[-1] if parts else ""
        first_author_family = first_author_family.lower().strip()

    title_norm = normalize_title(paper.title)
    year = str(paper.year) if paper.year is not None else _UNKNOWN_YEAR
    return f"{title_norm}|{first_author_family}|{year}"


def author_dedup_key(author: Author) -> str:
    """Prefer author_id when present; else (family, given) normalized."""
    if author.author_id:
        return author.author_id
    return normalize_author_name(author.family or "", author.given)


def institution_dedup_key(inst: Institution) -> str:
    """Prefer ROR > OpenAlex-like id > normalized display name.

    ``Institution`` has no dedicated ``openalex_id`` field on the model
    right now, so we treat ``institution_id`` as the provider-agnostic
    identifier fallback (covers OpenAlex and similar).
    """
    if inst.ror:
        return inst.ror
    if inst.institution_id:
        return inst.institution_id
    return normalize_title(inst.display_name)