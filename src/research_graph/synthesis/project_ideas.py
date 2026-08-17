"""research_graph.synthesis.project_ideas — generate ProjectIdea[] via LLM."""

from __future__ import annotations

import logging
import uuid

from research_graph.llm.base import LLMProvider, Message
from research_graph.llm.prompts import (
    PROJECT_IDEAS_SYSTEM,
    project_ideas_user_prompt,
)
from research_graph.models import ExtractionRecord, Paper, ProjectIdea


_log = logging.getLogger(__name__)


def _paper_summaries(papers: list[Paper], records: list[ExtractionRecord]) -> list[dict]:
    by_id = {r.paper_id: r for r in records}
    out: list[dict] = []
    for p in papers:
        r = by_id.get(p.paper_id)
        out.append({
            "id": p.paper_id,
            "title": p.title,
            "abstract": (p.abstract or "")[:1500],
            "key_concepts": r.research_area if r else [],
            "limitations": [lim.text for lim in (r.limitations if r else [])][:5],
        })
    return out


def propose(
    analysis: dict,
    papers: list[Paper],
    records: list[ExtractionRecord],
    llm: LLMProvider,
    n: int = 8,
    min_supporting: int = 2,
) -> list[ProjectIdea]:
    summaries = _paper_summaries(papers, records)
    prompt = project_ideas_user_prompt(summaries, n_ideas=n)
    try:
        result = llm.complete(
            [Message(role="system", content=PROJECT_IDEAS_SYSTEM),
             Message(role="user", content=prompt)],
            response_schema={"type": "object"},  # soft schema; defensive parse below
            temperature=0.3,
            max_tokens=4096,
        )
    except Exception as e:
        _log.warning(f"project_ideas: LLM call failed: {e}")
        return []

    if result.structured is None:
        return []

    ideas_raw = result.structured.get("ideas") if isinstance(result.structured, dict) else None
    if not isinstance(ideas_raw, list):
        return []

    accepted: list[ProjectIdea] = []
    for raw in ideas_raw:
        if not isinstance(raw, dict):
            continue
        sup = raw.get("supporting_papers") or []
        if not isinstance(sup, list) or len(sup) < min_supporting:
            _log.warning(f"project_ideas: idea {raw.get('project_title','?')} rejected (only {len(sup) if isinstance(sup,list) else 0} supporting papers)")
            continue
        # Generate an idea_id if missing
        if "idea_id" not in raw:
            raw["idea_id"] = str(uuid.uuid4())
        try:
            idea = ProjectIdea.model_validate(raw)
            accepted.append(idea)
        except Exception as e:
            _log.warning(f"project_ideas: rejected invalid idea: {e}")
    return accepted[:n]
