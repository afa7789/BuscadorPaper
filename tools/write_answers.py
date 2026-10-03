"""Write a batch of agent-LLM answers into output/agent_llm/answers/.

Input: a JSON file mapping request-id -> answer object (or string).
Every id must correspond to a file in output/agent_llm/requests/.

Usage:
  uv run python tools/write_answers.py answers_batch1.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQ = Path("output/agent_llm/requests")


def main() -> None:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    written, unknown = 0, []
    for rid, answer in payload.items():
        if not (REQ / f"{rid}.json").exists():
            unknown.append(rid)
            continue
        dest = Path("output/agent_llm/answers") / f"{rid}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        dest.write_text(body, encoding="utf-8")
        written += 1
    print(f"wrote {written} answers")
    if unknown:
        print(f"WARNING: {len(unknown)} ids not in queue: {unknown[:5]}")


if __name__ == "__main__":
    main()