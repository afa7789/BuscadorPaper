"""research_graph.synthesis.communities — per-community narrative."""

from __future__ import annotations

from collections import defaultdict

from research_graph.llm.base import LLMProvider, Message
from research_graph.llm.prompts import SYNTHESIS_SYSTEM


def narrate(analysis: dict, papers, llm: LLMProvider) -> dict[int, str]:
    """Return {community_id: ~80 word narrative} for each detected community."""
    communities = analysis.get("communities", {})
    grouped: dict[int, list[str]] = defaultdict(list)
    for pid, cid in communities.items():
        title = next((p.title for p in papers if p.paper_id == pid), pid)
        grouped[int(cid)].append(f"- {pid} | {title}")

    out: dict[int, str] = {}
    for cid, members in list(grouped.items())[:10]:
        prompt = (
            f"Community {cid} contains these papers:\n" + "\n".join(members) +
            "\n\nWrite an ~80-word narrative describing what binds them and what is distinctive."
        )
        try:
            r = llm.complete([
                Message(role="system", content=SYNTHESIS_SYSTEM),
                Message(role="user", content=prompt),
            ], max_tokens=300)
            out[cid] = r.content.strip() or "(no narrative)"
        except Exception:
            out[cid] = "(LLM unavailable; " + str(len(members)) + " papers in this community)"
    return out
