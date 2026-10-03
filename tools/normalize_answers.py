"""Coerce agent-LLM extraction answers into the ExtractionRecord schema.

The agent writes JSON by hand, so a scalar can land in a list-typed field
(e.g. `datasets_or_experimental_setup: "..."` instead of `["..."]`).
This script only normalises types -- it never edits prose.

Usage:
  uv run python tools/normalize_answers.py            # check + report
  uv run python tools/normalize_answers.py --write    # rewrite answers
"""
from __future__ import annotations

import glob
import json
import os
import sys

from pydantic import ValidationError

from research_graph.models import ExtractionRecord

LIST_FIELDS = [
    "research_area",
    "technical_components",
    "baseline_or_replaced_technique",
    "proposed_technique",
    "application_domain",
    "security_properties",
    "evaluation_metrics",
    "datasets_or_experimental_setup",
    "limitations",
    "future_work",
    "open_questions",
    "claims_with_evidence",
]
STR_FIELDS = ["problem", "main_contribution"]


def coerce(record: dict) -> dict:
    out = dict(record)
    for key in LIST_FIELDS:
        val = out.get(key)
        if val is None:
            out[key] = []
        elif isinstance(val, str):
            out[key] = [val] if val.strip() else []
        elif isinstance(val, dict):
            out[key] = [val]
    for key in STR_FIELDS:
        if not isinstance(out.get(key), str):
            out[key] = "" if out.get(key) is None else str(out[key])
    return out


def main() -> None:
    write = "--write" in sys.argv
    files = sorted(glob.glob("output/agent_llm/answers/*.txt"))
    bad: list[tuple[str, str]] = []
    fixed = 0
    for path in files:
        rid = os.path.basename(path)[:-4]
        raw = open(path, encoding="utf-8").read().strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            bad.append((rid, f"json: {exc}"))
            continue
        if not isinstance(data, dict):
            bad.append((rid, "not a JSON object"))
            continue
        coerced = coerce(data)
        if coerced != data:
            fixed += 1
            if write:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(coerced, fh, ensure_ascii=False, indent=1)
        try:
            ExtractionRecord.model_validate(coerced)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            bad.append((rid, f"{loc}: {first['msg'][:160]}"))

    print(f"files={len(files)} coerced={fixed} invalid={len(bad)}")
    for rid, msg in bad:
        print("  BAD", rid, msg)
    if bad and not write:
        print("\nre-run with --write after fixing the sources")


if __name__ == "__main__":
    main()