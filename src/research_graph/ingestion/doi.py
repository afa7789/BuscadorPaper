"""research_graph.ingestion.doi — DOI parsing + resolution.

The regex enforces the official DOI prefix (10. + registrant code 4-9 digits +
suffix). It rejects URLs that are missing the suffix or have trailing junk.
"""

from __future__ import annotations

import re
from typing import Optional

from research_graph.providers import ProviderRegistry
from research_graph.providers.base import ProviderResult


# Official DOI handbook syntax. 10.<registrant>/<suffix>.
# Suffix chars: any printable ASCII; we restrict to common ones to limit false positives.
_DOI_REGEX = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)

# URL patterns we strip before applying _DOI_REGEX
_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://www.doi.org/",
    "http://www.doi.org/",
    "doi:",
    "doi.org/",
)


def parse_doi(s: str) -> Optional[str]:
    """Parse a DOI string or DOI-URL into a bare DOI.

    Returns None for invalid / empty inputs. Strips common URL wrappers and
    lowercases. Validates the result against the strict regex.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for prefix in _URL_PREFIXES:
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip()
    if not s or "/" not in s:
        return None
    if not _DOI_REGEX.match(s):
        return None
    return s.lower()


_DOI_IN_TEXT_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def extract_doi_from_text(text: str) -> Optional[str]:
    """Find the first DOI-looking substring in free text."""
    if not text:
        return None
    m = _DOI_IN_TEXT_RE.search(text)
    return m.group(0).lower() if m else None


_ARXIV_IN_TEXT_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.IGNORECASE)


def extract_arxiv_from_text(text: str) -> Optional[str]:
    """Find the first arXiv id in free text."""
    if not text:
        return None
    m = _ARXIV_IN_TEXT_RE.search(text)
    return m.group(1) if m else None


def resolve_doi(doi: str, registry: ProviderRegistry) -> ProviderResult:
    """Walk the registry looking up a DOI; return first ok/partial."""
    from research_graph.providers import Resolver

    resolver = Resolver(registry)
    return resolver.resolve(lambda p: p.fetch_by_doi(doi))
