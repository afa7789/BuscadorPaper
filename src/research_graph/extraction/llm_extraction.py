"""research_graph.extraction.llm_extraction — call LLM to produce ExtractionRecord.

Defensive flow:
  1. Build prompt + schema.
  2. Call LLM (synchronous `complete`).
  3. If structured is None → return declared record with confidence=0.
  4. If ExtractionRecord.model_validate fails → return declared record with confidence=0.
  5. Else return the validated record (declared metadata overrides inferred when they disagree).

Cache: optional Cache keyed by "extraction:{paper_id}".
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from research_graph.cache import Cache
from research_graph.extraction.metadata import declared_to_extraction_record
from research_graph.llm.base import LLMProvider, Message
from research_graph.llm.prompts import EXTRACT_SYSTEM, paper_extraction_user_prompt
from research_graph.models import ExtractionRecord, Paper


_log = logging.getLogger(__name__)


def _cache_key(paper: Paper) -> str:
    payload = {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "abstract": (paper.abstract or "")[:4000],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "extraction:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def extract(paper: Paper, llm: LLMProvider, cache: Cache | None = None) -> ExtractionRecord:
    if cache is not None:
        hit = cache.get(_cache_key(paper))
        if hit is not None and hit[0] == "ok" and isinstance(hit[1], dict):
            try:
                return ExtractionRecord.model_validate(hit[1])
            except Exception:
                pass  # fall through

    prompt = paper_extraction_user_prompt(paper)
    messages = [
        Message(role="system", content=EXTRACT_SYSTEM),
        Message(role="user", content=prompt),
    ]
    schema = ExtractionRecord.model_json_schema()
    try:
        result = llm.complete(messages, response_schema=schema)
    except Exception as e:
        _log.warning(f"LLM extraction failed for {paper.paper_id}: {e}")
        rec = declared_to_extraction_record(paper)
        rec.extraction_confidence = 0.0
        return rec

    if result.structured is None:
        rec = declared_to_extraction_record(paper)
        rec.extraction_confidence = 0.0
        return rec

    try:
        rec = ExtractionRecord.model_validate(result.structured)
    except Exception as e:
        _log.warning(f"ExtractionRecord validation failed for {paper.paper_id}: {e}")
        rec = declared_to_extraction_record(paper)
        rec.extraction_confidence = 0.0
        return rec

    # Declared metadata overrides inferred
    if paper.year is not None:
        rec.year = paper.year if hasattr(rec, "year") else paper.year
    if paper.doi:
        # No doi field in ExtractionRecord; provenance note on the first claim's evidence_location
        pass

    if cache is not None:
        try:
            cache.set(_cache_key(paper), rec.model_dump(mode="json"), status="ok", source="llm")
        except Exception:
            pass

    return rec
