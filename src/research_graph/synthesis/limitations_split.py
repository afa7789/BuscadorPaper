"""research_graph.synthesis.limitations_split — declared vs inferred separation."""

from __future__ import annotations

from research_graph.models import ExtractionRecord, Origin


def render(records: list[ExtractionRecord], llm=None) -> dict:
    """Split limitations into declared (from paper) vs inferred (from LLM)."""
    declared: list[dict] = []
    inferred: list[dict] = []
    for r in records:
        for lim in r.limitations:
            entry = {"text": lim.text, "paper_id": r.paper_id,
                     "source_location": lim.evidence_location,
                     "confidence": lim.confidence}
            if lim.origin == Origin.DECLARED:
                declared.append(entry)
            else:
                inferred.append(entry)
    # Claims: same split
    for r in records:
        for c in r.claims_with_evidence:
            entry = {"text": c.claim, "paper_id": r.paper_id,
                     "evidence_type": c.evidence_type,
                     "source_location": c.source_location,
                     "confidence": c.confidence}
            if c.origin == Origin.DECLARED:
                declared.append(entry)
            else:
                inferred.append(entry)
    return {"declared": declared, "inferred": inferred}
