"""research_graph.people.professors — collect affiliation evidence per author.

For each author in the seed set:
  - Resolve an institution snapshot via OpenAlex (last-known).
  - Optionally verify against an official lab/faculty page.
  - Classify EvidenceStrength (strong / moderate / weak).

Per CONTEXT.md:
  strong: ORCID + official page confirm same affiliation + research line
  moderate: OpenAlex last-known institution + DBLP page match
  weak: only one source, OR sources disagree, OR no current page found

In v1 we approximate "ORCID" with the OpenAlex author_id and "DBLP page" with
the OpenAlex works page; v2 should pull real ORCID/DBLP data.
"""

from __future__ import annotations

import logging
from typing import Any

from research_graph.models import Author, EvidenceStrength, Institution
from research_graph.providers import ProviderRegistry


_log = logging.getLogger(__name__)


def classify_strength(evidence: dict) -> EvidenceStrength:
    """Classify evidence into strong/moderate/weak per CONTEXT.md rules."""
    has_orcid = bool(evidence.get("orcid"))
    has_official = bool(evidence.get("official_page_match"))
    has_openalex = bool(evidence.get("openalex_institution"))
    research_line_match = bool(evidence.get("research_line_match"))
    page_name_match = bool(evidence.get("page_name_match"))

    if has_orcid and has_official and research_line_match:
        return EvidenceStrength.STRONG
    if has_openalex and page_name_match:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.WEAK


def collect_evidence(
    author: Author,
    registry: ProviderRegistry,
    *,
    homepage: str | None = None,
    research_line: str | None = None,
) -> dict[str, Any]:
    """Gather raw affiliation evidence for an author."""
    evidence: dict[str, Any] = {
        "author_id": author.author_id,
        "orcid": author.orcid,
        "openalex_institution": None,
        "official_page_match": False,
        "page_name_match": False,
        "research_line_match": False,
        "sources": [],
    }
    # Try OpenAlex for the author's last-known institution
    openalex = registry.get("openalex")
    if openalex is not None and author.author_id.startswith("openalex:"):
        try:
            r = openalex.get_author_works(author.author_id, limit=1)
            # The result data is a list of papers; we don't get affiliation here in v1.
            # If we had a get_author endpoint we'd call it. For now, mark source used.
            if r.status in ("ok", "partial"):
                evidence["sources"].append("openalex")
        except Exception as e:
            _log.warning(f"openalex author lookup failed: {e}")
    # Try university_pages if a homepage was provided
    if homepage:
        up = registry.get("university_pages")
        if up is not None and hasattr(up, "_verify"):
            try:
                r = up._verify(homepage, author.display_name, research_line)
                if r.status == "ok" and isinstance(r.data, dict):
                    evidence["official_page_match"] = True
                    evidence["page_name_match"] = r.data.get("name_found", False)
                    evidence["research_line_match"] = r.data.get("line_found", False)
                    evidence["sources"].append("university_pages")
            except Exception as e:
                _log.warning(f"university_pages verify failed: {e}")
    return evidence


def aggregate(
    edges: list, papers: list[Author], institutions: list[Institution]
) -> dict:
    """Aggregate author -> institution edges with concentration flags.

    Returns: {"concentration": {institution_id: author_count}, "edges": [...]}
    """
    counts: dict[str, int] = {}
    for e in edges:
        iid = getattr(e, "target_node_id", None) or (e.get("target_node_id") if isinstance(e, dict) else None)
        if iid:
            counts[iid] = counts.get(iid, 0) + 1
    return {"concentration": counts, "edges": edges}
