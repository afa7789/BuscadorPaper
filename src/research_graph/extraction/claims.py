"""research_graph.extraction.claims — declared-vs-inferred classifier pass.

This stage runs AFTER the main LLM extraction. It walks the record's
``claims_with_evidence`` list and asks a small LLM call to label each
claim as ``declared`` (text appears in the paper itself) or ``inferred``
(model-derived synthesis). The result feeds the "Declared vs Inferred"
axis on every downstream claim, limitation, and open-problem.

Failure policy:
  - No claims / zero confidence: return record unchanged (no work to do).
  - LLM returns invalid JSON: return record unchanged (don't crash the
    pipeline on a bad response; the declared baseline already covers us).
  - LLM raises: log warning, return record unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from research_graph.models import ClaimWithEvidence, ExtractionRecord, Origin

logger = logging.getLogger(__name__)


# ---------- Sibling-module re-exports ---------------------------------------
#
# Imported under aliases so internal call-sites can use short names without
# shadowing the public API names (``LLMProvider``, ``Cache``) that the type
# annotations on ``classify`` refer to.

from research_graph.cache import Cache as _Cache  # noqa: E402
from research_graph.llm.base import LLMProvider as _LLMProvider  # noqa: E402
from research_graph.llm.base import Message as _Message  # noqa: E402
from research_graph.llm.prompts import CLAIMS_SYSTEM as _CLAIMS_SYSTEM  # noqa: E402


# ---------- Prompt + response shape -----------------------------------------

def _claims_user_prompt(claims: list[ClaimWithEvidence]) -> str:
    """Build the user-message payload sent to the claims-classifier LLM."""
    payload = [
        {
            "index": i,
            "claim": c.claim,
            "evidence_type": c.evidence_type,
            "source_location": c.source_location,
        }
        for i, c in enumerate(claims)
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _cache_key(record: ExtractionRecord, prompt: str) -> str:
    """Stable hash of (paper_id, prompt) for the claims-classifier cache."""
    h = hashlib.sha256()
    h.update(record.paper_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return f"claims:{record.paper_id}:{h.hexdigest()[:16]}"


def _parse_classifications(
    raw: Any, n_claims: int
) -> list[dict[str, Any]] | None:
    """Coerce an LLM response into a list of {index, source, confidence}.

    Returns None on any structural problem so the caller can short-circuit.
    Accepts either a JSON string or a pre-parsed list/dict.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if isinstance(raw, dict):
        # some providers wrap the payload in a top-level key
        for key in ("classifications", "items", "results"):
            if key in raw and isinstance(raw[key], list):
                raw = raw[key]
                break
        else:
            return None
    if not isinstance(raw, list):
        return None

    cleaned: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            return None
        if "claim_index" not in entry and "index" in entry:
            entry["claim_index"] = entry["index"]
        if "source" not in entry and "label" in entry:
            entry["source"] = entry["label"]
        if "claim_index" not in entry or "source" not in entry:
            return None
        try:
            idx = int(entry["claim_index"])
        except (TypeError, ValueError):
            return None
        if idx < 0 or idx >= n_claims:
            return None
        cleaned.append(
            {
                "claim_index": idx,
                "source": str(entry["source"]).lower().strip(),
                "confidence": entry.get("confidence"),
            }
        )
    return cleaned


def _source_to_origin(source: str) -> Origin:
    """Map the LLM's free-text source label to the Origin enum."""
    s = source.lower().strip()
    if s in ("declared", "explicit", "stated", "text"):
        return Origin.DECLARED
    if s in ("inferred", "derived", "synthesized", "synthesis"):
        return Origin.INFERRED
    # Unknown label: keep the declared default; downstream can re-classify.
    return Origin.DECLARED


# ---------- Public API --------------------------------------------------------

def classify(
    record: ExtractionRecord,
    llm: "LLMProvider",
    cache: "Cache | None" = None,
) -> ExtractionRecord:
    """Re-label each claim's ``origin`` based on a small LLM classification.

    Returns the input record unchanged when:
      - there are no claims to classify
      - extraction_confidence is 0 (declared baseline only, nothing to do)
      - the LLM raises or returns invalid JSON (warning logged)
    """
    if not record.claims_with_evidence or record.extraction_confidence == 0:
        return record

    user_prompt = _claims_user_prompt(record.claims_with_evidence)
    key = _cache_key(record, user_prompt)

    cached: Any = None
    if cache is not None:
        try:
            cached = cache.get(key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("claims cache.get failed: %s", exc)

    raw_response: Any
    if cached is not None:
        raw_response = cached
    else:
        try:
            result = llm.complete(
                [
                    _Message(role="system", content=_CLAIMS_SYSTEM),
                    _Message(role="user", content=user_prompt),
                ],
                response_schema=_CLAIMS_RESPONSE_SCHEMA,
            )
        except Exception as exc:
            logger.warning("claims LLM call failed: %s", exc)
            return record

        # ``result`` shape is provider-defined. We accept both a structured
        # field and a string content field, whichever the provider gave us.
        raw_response = (
            getattr(result, "structured", None)
            or getattr(result, "content", None)
            or getattr(result, "text", None)
        )

        if cache is not None and raw_response is not None:
            try:
                cache.set(key, raw_response, status="ok")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("claims cache.set failed: %s", exc)

    parsed = _parse_classifications(raw_response, len(record.claims_with_evidence))
    if parsed is None:
        logger.warning(
            "claims classifier returned invalid JSON for paper %s; "
            "leaving claims unchanged",
            record.paper_id,
        )
        return record

    # Apply the labels in-place. We rebuild the list because ClaimWithEvidence
    # is a pydantic model and pydantic v2 supports copy/update but not
    # in-place mutation of validated fields.
    updated: list[ClaimWithEvidence] = list(record.claims_with_evidence)
    for entry in parsed:
        idx = entry["claim_index"]
        origin = _source_to_origin(entry["source"])
        existing = updated[idx]
        new_conf = existing.confidence
        if entry.get("confidence") is not None:
            try:
                new_conf = float(entry["confidence"])
                new_conf = max(0.0, min(1.0, new_conf))
            except (TypeError, ValueError):
                pass
        updated[idx] = existing.model_copy(
            update={"origin": origin, "confidence": new_conf}
        )

    return record.model_copy(update={"claims_with_evidence": updated})


# JSON Schema for the claims classifier response. Kept inline so the file
# remains import-clean before research_graph.llm ships.
_CLAIMS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_index": {"type": "integer"},
                    "source": {
                        "type": "string",
                        "enum": ["declared", "inferred"],
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["claim_index", "source"],
            },
        }
    },
    "required": ["classifications"],
}