"""research_graph.llm.prompts — prompt strings and helper builders.

Four system prompts plus two user-prompt builders. NO template engine: the
helpers use Python f-string formatting at the call site. The ``TYPE_CHECKING``
import for ``Paper`` keeps this module importable without pulling models
into a circular dep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research_graph.models import Paper


EXTRACT_SYSTEM: str = """You are a careful research-paper analyst.

Your task: extract structured information from the paper provided.

Rules:
1. Output MUST be valid JSON matching the ExtractionRecord schema (provided separately).
2. For each claim, mark it `declared` (text appears in the paper) vs `inferred` (your conclusion).
3. Every claim MUST include `evidence_type` and `source_location` (e.g. "Section 4.2", "abstract", "Table 3").
4. If you are not confident in a field, omit it or set extraction_confidence < 0.5.
5. Never invent DOIs, paper_ids, or citation counts. If you do not know, omit the field.
6. Limitations and Future Work are TWO DIFFERENT categories:
   - Limitations = weaknesses the paper admits (e.g. "our proof requires a trusted setup").
   - Future Work = directions the paper explicitly suggests.
   Do not mix them.
7. Output the JSON object directly — no prose, no markdown fencing, no commentary."""


CLAIMS_SYSTEM: str = """You re-classify research-paper claims.

For each claim provided, decide whether it is `declared` (the paper itself asserts this)
or `inferred` (the claim is your interpretation or extrapolation).

Output JSON: {"claims": [{"text": str, "origin": "declared"|"inferred",
"evidence_type": str, "source_location": str, "confidence": float}]}.

Be conservative: if a claim paraphrases the paper but is not a direct quote, mark it `inferred`."""


SYNTHESIS_SYSTEM: str = """You write the executive summary of a literature graph.

Given:
- Community summaries (one per Louvain community of related papers).
- Seed papers (the input the user provided).

Produce JSON with EXACTLY these keys:
  - "executive_summary": string (max ~500 words, technical, in the project's language).
  - "how_seeds_connect": string (max ~200 words; trace the paths between seed papers).
  - "per_community_narrative": object mapping community_id (int as string) to ~80 words each.

Stay grounded: cite paper_ids when making claims. Do not invent facts not in the inputs.
The output language is the project's language (pt-BR by default; English if config says so)."""


PROJECT_IDEAS_SYSTEM: str = """You propose concrete research projects derived from a literature map.

Each project MUST satisfy:
- `research_problem`: a specific technical problem (not "use blockchain for X").
- `baseline`: a known technique or system to compare against.
- `proposed_change`: a concrete modification.
- `property_to_prove_or_measure`: e.g. "soundness", "prover time", "verifier time", "TPS".
- `evaluation_metrics`: list, e.g. ["proving time (s)", "verifier gas cost"].
- `supporting_papers`: list of paper_ids (string) from the input graph. MUST be >= 2.
- `confidence`: float in [0, 1] reflecting how strongly the literature supports the idea.

Output JSON: {"ideas": [<ProjectIdea>, ...]} — at most n_ideas objects.

Reject ideas that:
- Lack a concrete proposed_change.
- Cite fewer than 2 supporting_papers from the input.
- Use vague language like "explore" or "investigate" without a measurable outcome."""


def paper_extraction_user_prompt(paper: "Paper", abstract_limit: int = 4000) -> str:
    """Build the user message for the extraction stage.

    Includes title, authors, year, venue, DOI, and abstract (truncated).
    Ends with an explicit "return JSON only" footer.
    """
    abstract = (paper.abstract or "")[:abstract_limit]
    if paper.abstract and len(paper.abstract) > abstract_limit:
        abstract += "... [truncated]"
    doi_line = f"DOI: {paper.doi}\n" if paper.doi else ""
    venue_line = f"Venue: {paper.venue}\n" if paper.venue else ""
    authors_line = (
        f"Authors: {', '.join(paper.authors)}\n" if paper.authors else ""
    )
    return (
        f"Paper: {paper.title}\n"
        f"Year: {paper.year or 'unknown'}\n"
        f"{doi_line}{venue_line}{authors_line}\n"
        f"Abstract:\n{abstract or '(no abstract provided)'}\n\n"
        "Return a single JSON object matching the ExtractionRecord schema. "
        "Do not include any text outside the JSON."
    )


def project_ideas_user_prompt(paper_summaries: list[dict], n_ideas: int = 8) -> str:
    """Build the user message for project-idea synthesis.

    ``paper_summaries`` is a list of dicts with keys:
      id, title, abstract, key_concepts, limitations
    """
    lines: list[str] = []
    lines.append(f"Generate up to {n_ideas} concrete research project ideas from this literature map.")
    lines.append("Each idea MUST cite at least 2 of the paper_ids below.\n")
    for ps in paper_summaries:
        lines.append(f"--- paper_id: {ps.get('id')} ---")
        lines.append(f"Title: {ps.get('title', '')}")
        if ps.get("abstract"):
            lines.append(f"Abstract: {ps['abstract']}")
        if ps.get("key_concepts"):
            lines.append(f"Key concepts: {', '.join(ps['key_concepts'])}")
        if ps.get("limitations"):
            lines.append(f"Limitations: {'; '.join(ps['limitations'])}")
        lines.append("")
    lines.append('Output JSON: {"ideas": [<ProjectIdea>, ...]}. Do not include prose outside the JSON.')
    return "\n".join(lines)


__all__ = [
    "EXTRACT_SYSTEM",
    "CLAIMS_SYSTEM",
    "SYNTHESIS_SYSTEM",
    "PROJECT_IDEAS_SYSTEM",
    "paper_extraction_user_prompt",
    "project_ideas_user_prompt",
]
