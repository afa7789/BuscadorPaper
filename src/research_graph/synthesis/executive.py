"""research_graph.synthesis.executive — executive summary + how-seeds-connect."""

from __future__ import annotations

from research_graph.llm.base import LLMProvider, Message
from research_graph.llm.prompts import SYNTHESIS_SYSTEM


def summary(analysis: dict, papers, llm: LLMProvider) -> str:
    """Return a Markdown executive summary string. Falls back to a basic
    structural summary if the LLM is unavailable or returns nothing."""
    top = sorted(
        analysis.get("centrality", {}).items(),
        key=lambda kv: kv[1].get("pagerank", 0),
        reverse=True,
    )[:5]
    fallback_lines: list[str] = ["# Executive Summary\n"]
    for pid, cent in top:
        title = next((p.title for p in papers if p.paper_id == pid), pid)
        fallback_lines.append(f"- **{title}** (PageRank {cent.get('pagerank', 0):.3f})")
    fallback_lines.append(
        f"\n*Centrality is structural prominence, not quality. "
        f"{analysis.get('meta', {}).get('node_count', 0)} nodes, "
        f"{analysis.get('meta', {}).get('community_count', 0)} communities.*"
    )
    fallback = "\n".join(fallback_lines)

    try:
        user_prompt = _build_user_prompt(analysis, papers)
        result = llm.complete(
            [Message(role="system", content=SYNTHESIS_SYSTEM),
             Message(role="user", content=user_prompt)],
        )
        if result.content and result.content.strip():
            return result.content
    except Exception:
        pass
    return fallback


def _build_user_prompt(analysis: dict, papers) -> str:
    lines = ["Top papers by PageRank:"]
    top = sorted(analysis.get("centrality", {}).items(),
                 key=lambda kv: kv[1].get("pagerank", 0), reverse=True)[:10]
    for pid, cent in top:
        title = next((p.title for p in papers if p.paper_id == pid), pid)
        lines.append(f"- {pid} | {title} | PageRank={cent.get('pagerank', 0):.3f}")
    lines.append("\nCommunities:")
    comm = analysis.get("communities", {})
    for pid, cid in list(comm.items())[:20]:
        lines.append(f"- {pid} -> community {cid}")
    lines.append("\nProduce the executive_summary + how_seeds_connect + per_community_narrative JSON.")
    return "\n".join(lines)
