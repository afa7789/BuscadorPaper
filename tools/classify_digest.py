"""Compact digest of queued claims-classification requests.

Usage:
  uv run python tools/classify_digest.py           # all
  uv run python tools/classify_digest.py 0 20      # items 0..20
"""
from __future__ import annotations

import glob
import json
import os
import sys

CLIMIT = int(os.environ.get("CLIMIT", "260"))


def main() -> None:
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    stop = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
    files = sorted(glob.glob("output/agent_llm/requests/*.json"))
    for i, f in enumerate(files):
        if not (start <= i < stop):
            continue
        d = json.load(open(f, encoding="utf-8"))
        user = d["messages"][1]["content"]
        claims = json.loads(user)
        print(f"### [{i}] id={d['id']} n={len(claims)}")
        for c in claims:
            print(f"  [{c['index']}] {c['evidence_type']} | {c['claim'][:CLIMIT]}")
            print(f"      loc: {c['source_location'][:CLIMIT]}")
        print()


if __name__ == "__main__":
    main()