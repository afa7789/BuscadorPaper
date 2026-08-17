"""research_graph.reports.markdown — render the 13-section Markdown report.

Sections (in order):
  1. Scope
  2. Seeds
  3. Discovered Papers
  4. Graph Overview (with centrality table + disclaimer)
  5. Communities
  6. Researchers
  7. Methods & Replacements
  8. Declared vs Inferred Limitations
  9. Open Questions
  10. Project Ideas (by difficulty)
  11. Recommendation
  12. Evolution
  13. Risks, Biases, and Limitations of the Mapping Itself
  ## References
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import networkx as nx

from research_graph.config import Config
from research_graph.models import ExtractionRecord, Paper


# ---------- Section renderers -------------------------------------------------

def render_scope(config: Config) -> str:
    p = config.project
    s = config.research_scope
    lines = ["# 1. Scope\n"]
    lines.append(f"**Project:** {p.name}")
    lines.append(f"**Language:** {p.language}")
    lines.append(f"**Output dir:** `{p.output_dir}`\n")
    lines.append("**Research scope:**")
    if s.seed_keywords:
        lines.append(f"- Seed keywords: {', '.join(s.seed_keywords)}")
    if s.include_domains:
        lines.append(f"- Include domains: {', '.join(s.include_domains)}")
    lines.append(f"- Year window: {s.years_from} – {s.years_to}")
    lines.append(f"- Max hops: {s.max_hops}, max total papers: {s.max_total_papers}")
    lines.append(f"- Min relevance score: {s.min_relevance_score}")
    return "\n".join(lines) + "\n"


def render_seeds(papers: list[Paper], config: Config) -> str:
    lines = ["# 2. Seed Papers\n"]
    seed_values = [s.value for s in config.seed_inputs]
    seed_papers = [p for p in papers if any(s in p.urls or s == p.paper_id for s in seed_values)]
    if not seed_papers:
        lines.append("_No seed papers resolved yet. Run `research-graph ingest` first._")
    else:
        for p in seed_papers:
            doi = f" (DOI: {p.doi})" if p.doi else ""
            yr = f" [{p.year}]" if p.year else ""
            lines.append(f"- **{p.title}**{yr}{doi}")
    return "\n".join(lines) + "\n"


def render_discovered(papers: list[Paper]) -> str:
    lines = [f"# 3. Discovered Papers\n", f"Total after dedup + expansion: **{len(papers)}**\n"]
    for p in sorted(papers, key=lambda x: x.year or 0, reverse=True)[:40]:
        yr = f"[{p.year}]" if p.year else "[—]"
        doi = f" — DOI: {p.doi}" if p.doi else ""
        lines.append(f"- {yr} **{p.title}**{doi}")
    return "\n".join(lines) + "\n"


def render_graph_overview(graph: nx.MultiDiGraph, analysis: dict) -> str:
    meta = analysis.get("meta", {})
    centrality = analysis.get("centrality", {})
    lines = ["# 4. Graph Overview\n"]
    lines.append(f"- Nodes: **{meta.get('node_count', 0)}**")
    lines.append(f"- Edges: **{meta.get('edge_count', 0)}**")
    lines.append(f"- Communities (Louvain): **{meta.get('community_count', 0)}**")
    lines.append(f"- Weak components: **{meta.get('weak_component_count', 0)}**\n")
    lines.append("**Disclaimer:** Centrality is structural prominence, not quality. It measures position in the network, not validity, impact, or excellence.\n")
    if centrality:
        lines.append("\n### Top 10 by PageRank\n")
        lines.append("| paper_id | degree | betweenness | pagerank |")
        lines.append("|----------|--------|-------------|----------|")
        top = sorted(centrality.items(), key=lambda kv: kv[1].get("pagerank", 0), reverse=True)[:10]
        for pid, c in top:
            lines.append(f"| {pid[:50]} | {c.get('degree', 0):.3f} | {c.get('betweenness', 0):.3f} | {c.get('pagerank', 0):.3f} |")
    lines.append("\n_Interactive HTML: `graph.html`. Mermaid: `graph.mmd`._")
    return "\n".join(lines) + "\n"


def render_communities(analysis: dict, synthesis: dict) -> str:
    lines = ["# 5. Communities\n"]
    comm = analysis.get("communities", {})
    narratives = synthesis.get("per_community_narrative", {})
    if not comm:
        lines.append("_No communities detected._")
        return "\n".join(lines) + "\n"
    grouped: dict[int, list[str]] = {}
    for pid, cid in comm.items():
        grouped.setdefault(int(cid), []).append(pid)
    for cid in sorted(grouped):
        lines.append(f"## Community {cid} ({len(grouped[cid])} papers)")
        if cid in narratives:
            lines.append(f"\n{narratives[cid]}\n")
        for pid in grouped[cid][:8]:
            lines.append(f"- {pid}")
        if len(grouped[cid]) > 8:
            lines.append(f"- _(+{len(grouped[cid]) - 8} more)_")
    return "\n".join(lines) + "\n"


def render_researchers(people: dict) -> str:
    lines = ["# 6. Researchers\n"]
    if not people:
        lines.append("_No researcher data collected yet. Run `people` stage or enable `search.professor_search`._")
        return "\n".join(lines) + "\n"
    by_strength: dict[str, list[dict]] = {}
    for r in people:
        s = r.get("strength", "weak")
        by_strength.setdefault(s, []).append(r)
    for s in ("strong", "moderate", "weak"):
        if s in by_strength:
            lines.append(f"\n## Evidence strength: {s} ({len(by_strength[s])})\n")
            for r in by_strength[s][:20]:
                ev = r.get("evidence", {})
                sources = ", ".join(ev.get("sources", [])) or "—"
                lines.append(f"- **{r.get('author','?')}** — sources: {sources}")
    return "\n".join(lines) + "\n"


def render_methods_replacements(graph: nx.MultiDiGraph, records: list[ExtractionRecord]) -> str:
    lines = ["# 7. Methods & Replacements\n"]
    # For each paper, list proposed techniques and their "baseline"
    rows: list[tuple[str, str, str]] = []
    for r in records:
        for prop in r.proposed_technique:
            baseline = "; ".join(r.baseline_or_replaced_technique) or "(none stated)"
            rows.append((r.paper_id, prop, baseline))
    if not rows:
        lines.append("_No method-level data extracted yet._")
        return "\n".join(lines) + "\n"
    lines.append("| paper_id | proposed technique | baseline |")
    lines.append("|----------|--------------------|----------|")
    for pid, prop, baseline in rows[:30]:
        lines.append(f"| {pid[:40]} | {prop[:50]} | {baseline[:50]} |")
    return "\n".join(lines) + "\n"


def render_declared_vs_inferred(synthesis: dict) -> str:
    lines = ["# 8. Declared vs Inferred Limitations\n"]
    dvi = synthesis.get("declared_vs_inferred", {})
    lines.append(f"\n## Declared by papers (n={len(dvi.get('declared', []))})\n")
    for entry in dvi.get("declared", [])[:15]:
        lines.append(f"- **[{entry['paper_id']}]** {entry['text'][:200]} _(loc: {entry.get('source_location','?')})_")
    lines.append(f"\n## Inferred by LLM (n={len(dvi.get('inferred', []))})\n")
    for entry in dvi.get("inferred", [])[:15]:
        lines.append(f"- **[{entry['paper_id']}]** {entry['text'][:200]} _(confidence {entry.get('confidence', 0):.2f})_")
    return "\n".join(lines) + "\n"


def render_open_questions(records: list[ExtractionRecord]) -> str:
    lines = ["# 9. Open Questions\n"]
    qs: list[tuple[str, str]] = []
    for r in records:
        for op in r.open_questions:
            qs.append((r.paper_id, op.statement))
    if not qs:
        lines.append("_No open questions extracted yet._")
        return "\n".join(lines) + "\n"
    seen: set[str] = set()
    for pid, q in qs:
        if q in seen:
            continue
        seen.add(q)
        lines.append(f"- **[{pid}]** {q[:300]}")
    return "\n".join(lines) + "\n"


def render_ideas_by_difficulty(synthesis: dict) -> str:
    lines = ["# 10. Project Ideas (by difficulty)\n"]
    ideas = synthesis.get("project_ideas", [])
    if not ideas:
        lines.append("_No project ideas generated (LLM may be disabled or no papers)._")
        return "\n".join(lines) + "\n"
    by_diff: dict[str, list[dict]] = {"low": [], "medium": [], "high": []}
    for idea in ideas:
        by_diff.setdefault(idea.get("difficulty", "medium"), []).append(idea)
    for diff in ("low", "medium", "high"):
        bucket = by_diff[diff]
        if not bucket:
            continue
        lines.append(f"\n## Difficulty: {diff} ({len(bucket)})\n")
        for idea in bucket:
            lines.append(f"\n### {idea.get('project_title','(untitled)')}")
            lines.append(f"\n_{idea.get('one_sentence_proposal','')}_\n")
            lines.append(f"- **Problem:** {idea.get('research_problem','')}")
            lines.append(f"- **Baseline:** {idea.get('baseline','')}")
            lines.append(f"- **Proposed change:** {idea.get('proposed_change','')}")
            lines.append(f"- **Property to prove/measure:** {idea.get('property_to_prove_or_measure','')}")
            lines.append(f"- **Master thesis fit:** {idea.get('master_thesis_fit','')}")
            lines.append(f"- **Confidence:** {idea.get('confidence', 0):.2f}")
            sp = idea.get("supporting_papers") or []
            if sp:
                lines.append(f"- **Supporting papers:** {', '.join(sp[:5])}")
    return "\n".join(lines) + "\n"


def render_recommendation(synthesis: dict) -> str:
    lines = ["# 11. Recommendation\n"]
    ideas = synthesis.get("project_ideas", [])
    if not ideas:
        lines.append("_No project ideas to recommend. Run synthesis with LLM enabled._")
        return "\n".join(lines) + "\n"
    # Pick highest-confidence "medium"-difficulty idea with master_thesis_fit != "low"
    candidates = [
        i for i in ideas
        if i.get("master_thesis_fit") in ("medium", "high")
        and i.get("confidence", 0) >= 0.5
    ]
    if not candidates:
        candidates = ideas
    best = max(candidates, key=lambda i: i.get("confidence", 0))
    lines.append(f"**Recommended thesis topic:** {best.get('project_title','(untitled)')}\n")
    lines.append(f"_{best.get('one_sentence_proposal','')}_\n")
    lines.append(f"\n**Why:** confidence {best.get('confidence', 0):.2f}, "
                 f"difficulty {best.get('difficulty','')}, "
                 f"master-thesis fit {best.get('master_thesis_fit','')}.")
    return "\n".join(lines) + "\n"


def render_evolution() -> str:
    return ("# 12. Evolution\n\n"
            "The pipeline currently produces a single snapshot per run. "
            "Tracking changes across runs (new papers, communities merging, "
            "idea confidence shifting) is on the roadmap; until then, "
            "compare `output/analysis.json` across runs manually.\n")


def render_risks_biases() -> str:
    return (
        "# 13. Risks, Biases, and Limitations of the Mapping Itself\n\n"
        "**Coverage bias.** The map reflects what the academic APIs know. "
        "Preprints without DOIs, gray literature, and non-English venues "
        "may be under-represented.\n\n"
        "**Provider failure tolerance.** Each stage logs provider failures "
        "and continues; a single source outage does NOT abort the run, but "
        "may leave gaps in the graph.\n\n"
        "**Centrality ≠ quality.** PageRank, betweenness, and degree measure "
        "position in the network. They say nothing about scientific validity, "
        "rigor, or real-world impact.\n\n"
        "**Stale affiliations.** Author→institution edges use the last-known "
        "affiliation from OpenAlex; researchers who have moved may be "
        "mis-attributed. Strength classification (strong / moderate / weak) "
        "encodes evidence quality but cannot fully correct this.\n\n"
        "**LLM fabrication risk.** Project ideas and synthesis text are "
        "LLM-generated. Ideas citing fewer than 2 supporting papers are "
        "rejected at synthesis time; all remaining ideas are explicitly "
        "labeled with confidence, and declared limitations are kept "
        "separate from inferred ones.\n\n"
        "**No Google Scholar.** Per terms of use and absence of a public "
        "API, Google Scholar is not scraped. If you have Scholar exports, "
        "paste them into `seed_inputs` as `doi`/`title` and the providers "
        "above will resolve them.\n\n"
        "**Costs.** The free academic APIs (OpenAlex, Semantic Scholar, "
        "Crossref, arXiv) cover all stages except LLM synthesis. LLM "
        "calls dominate cost; pass `--no-llm` to skip them.\n\n"
        "**OpenAlex limits.** OpenAlex exposes roughly 240M works, but "
        "endpoint-specific limits apply: search returns at most 200 "
        "per page, citation lookups paginate at 200 per request, and "
        "the polite-pool (10 req/s with `OPENALEX_EMAIL` set) is the "
        "largest available tier. Free-tier IPs can be throttled without "
        "warning after high-volume bursts. Coverage is strong for "
        "English-language works with DOIs; weaker for theses, "
        "non-English papers, and very recent preprints.\n\n"
        "**Anna's Archive and Sci-Hub coverage.** These opt-in "
        "providers index papers through shadow-library mirrors; they "
        "give *some* full-text PDFs that OpenAlex cannot, but coverage "
        "is uneven. They are aimed at personal research access; verify "
        "your local jurisdiction's stance on copyrighted works before "
        "enabling. The program never uses them by default — you must "
        "opt in via `enable_pdf_download: true` in `config.yaml`.\n"
    )


def render_references(papers: list[Paper]) -> str:
    lines = ["## References\n"]
    seen: set[str] = set()
    for p in sorted(papers, key=lambda x: (x.year or 0, x.title), reverse=True):
        if p.paper_id in seen:
            continue
        seen.add(p.paper_id)
        yr = f"{p.year}. " if p.year else ""
        doi_link = f" https://doi.org/{p.doi}" if p.doi else ""
        url = (p.urls[0] if p.urls else "")
        url_part = f" {url}" if url else ""
        lines.append(f"- {yr}**{p.title}**{doi_link}{url_part}")
    return "\n".join(lines) + "\n"


# ---------- Top-level render --------------------------------------------------

def render(
    config: Config,
    graph: nx.MultiDiGraph,
    analysis: dict,
    synthesis: dict,
    papers: list[Paper],
    records: list[ExtractionRecord],
    people: dict,
) -> str:
    parts: list[str] = []
    parts.append(render_scope(config))
    parts.append(render_seeds(papers, config))
    parts.append(render_discovered(papers))
    parts.append(render_graph_overview(graph, analysis))
    parts.append(render_communities(analysis, synthesis))
    parts.append(render_researchers(people))
    parts.append(render_methods_replacements(graph, records))
    parts.append(render_declared_vs_inferred(synthesis))
    parts.append(render_open_questions(records))
    parts.append(render_ideas_by_difficulty(synthesis))
    parts.append(render_recommendation(synthesis))
    parts.append(render_evolution())
    parts.append(render_risks_biases())
    parts.append(render_references(papers))
    return "\n".join(parts)
