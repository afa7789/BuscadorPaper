"""Compact digest of the queued agent-LLM requests, for reading in batches.

Usage:
  uv run python tools/queue_digest.py            # list all
  uv run python tools/queue_digest.py 0 20       # items 0..20
"""
from __future__ import annotations

import glob
import json
import sys

LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 1600


def main() -> None:
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    stop = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
    files = sorted(glob.glob("output/agent_llm/requests/*.json"))
    for i, f in enumerate(files):
        if not (start <= i < stop):
            continue
        d = json.load(open(f, encoding="utf-8"))
        msgs = d["messages"]
        user = msgs[1]["content"] if len(msgs) > 1 else msgs[0]["content"]
        head, _, abstract = user.partition("Abstract:\n")
        print(f"### [{i}] id={d['id']}  answer={d['answer_path']}")
        print(head.strip())
        print("ABSTRACT:", abstract.strip()[:LIMIT])
        print()


if __name__ == "__main__":
    main()