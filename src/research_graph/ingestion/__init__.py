"""research_graph.ingestion — public API and stage orchestrator.

Public API:
  - dispatch(entry, registry) -> list[Paper]
  - run_ingest(config, *, no_llm=False, continue_on_error=True) -> int

The orchestrator writes ``output_dir/papers.json`` (list of deduplicated Paper
records) and ``output_dir/ingest_summary.json`` with counts and timings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from research_graph.config import Config
from research_graph.ingestion.inputs import dispatch
from research_graph.ingestion.backfill import backfill_abstracts
from research_graph.ingestion.dedup import merge
from research_graph.ingestion.methodology import classify, screen
from research_graph.providers import get_default_registry
from research_graph.logging_setup import configure_logging
from research_graph.providers._atomic import atomic_write_text
from research_graph.papers_kv import write_papers_kv

_log = logging.getLogger(__name__)

# Seed types whose results are *discovered* rather than *named by the user*.
# Only these are subject to the research-design screen.
_QUERY_SEED_TYPES = {"crossref_query", "ddg_query", "tavily_query"}


def _citations(paper) -> int:
    """Best-effort citation count. Crossref/OpenAlex stash it in provenance."""
    raw = (paper.source_provenance or {}).get("citation_count")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _priority_key(paper):
    """Sort key for trimming to ``max_total_papers``: best-first, then paper_id.

    Deliberately *not* ``expansion.ranking``: its Jaccard relevance term scores
    a missing abstract as 0.0, which buries exactly the papers this corpus
    most wants (unabstracted but on-topic field research). Instead:

      1. explicit seeds first — they define the topic and are never trimmed away;
      2. ``primary`` (field research) before ``unknown``;
      3. has an abstract — the LLM extraction stage can only read that;
      4. more citations — established field research first;
      5. more recent; then paper_id for a deterministic tie-break.
    """
    return (
        0 if paper.get("is_seed") else 1,
        0 if paper.get("verdict") == "primary" else 1,
        0 if (paper["paper"].abstract or "").strip() else 1,
        -_citations(paper["paper"]),
        -(paper["paper"].year or 0),
        paper["paper"].paper_id or "",
    )


def trim_to_budget(
    papers,
    *,
    limit: int,
    seed_ids: set[str],
    verdicts: dict[str, str] | None = None,
):
    """Keep at most ``limit`` papers, dropping the weakest first.

    Papers whose id is in ``seed_ids`` (the documents the user named) are kept
    regardless of budget — dropping a user's own anchor silently would change
    the meaning of the whole run.
    """
    verdicts = verdicts or {}
    if limit <= 0 or len(papers) <= limit:
        return list(papers)
    tagged = [
        {"paper": p, "is_seed": p.paper_id in seed_ids, "verdict": verdicts.get(p.paper_id)}
        for p in papers
    ]
    tagged.sort(key=_priority_key)
    kept = [t["paper"] for t in tagged[:limit]]
    # Preserve the original ingest order so reruns stay diff-friendly.
    order = {p.paper_id: i for i, p in enumerate(papers)}
    kept.sort(key=lambda p: order.get(p.paper_id, 0))
    return kept


def _mark_explicit_seeds(merged, doc_papers) -> set[str]:
    """Tag ingest output: every paper anchors relevance, named documents rank first."""
    seed_ids = {p.paper_id for p in doc_papers}
    for p in merged:
        p.source_provenance["ingest_seed"] = "true"
        if p.paper_id in seed_ids:
            p.source_provenance["explicit_seed"] = "true"
    return seed_ids


def _reset_expand(out_dir: Path) -> None:
    """A new ingest is a new corpus: drop expand's resume point and links."""
    for name in ("expand_state.json", "links.json"):
        (out_dir / name).unlink(missing_ok=True)


def run_ingest(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Run the ingest stage: resolve seed_inputs -> dedup -> write JSON."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        registry = get_default_registry(config)
    except Exception as e:
        _log.error(f"ingest: failed to build provider registry: {e}")
        if not continue_on_error:
            return 1
        registry = None

    # Documents the user named explicitly are never screened: they are the
    # topic definition, not search output. Only query-derived hits are filtered.
    doc_papers: list = []
    query_papers: list = []
    for entry in config.seed_inputs:
        if registry is None:
            _log.warning(f"ingest: skipping {entry.type}={entry.value[:60]} (no registry)")
            continue
        papers = dispatch(entry, registry)
        _log.info(f"ingest: {entry.type}={entry.value[:60]} -> {len(papers)} papers")
        (query_papers if entry.type in _QUERY_SEED_TYPES else doc_papers).extend(papers)

    merged = merge(doc_papers + query_papers)
    _log.info(f"ingest: {len(doc_papers) + len(query_papers)} raw -> {len(merged)} after dedup")

    # Crossref often omits abstracts; without them the LLM extraction stage has
    # nothing to read and relevance ranking penalises the paper. Re-ask a
    # provider that carries abstracts before writing papers.json.
    if not no_llm and registry is not None:
        try:
            merged = backfill_abstracts(merged, registry, limit=int(
                getattr(config, "max_abstract_backfill", 120) or 120
            ))
        except Exception as e:
            _log.warning(f"ingest: abstract backfill skipped: {e}")

    design_counts = {"primary": 0, "documentary": 0, "unknown": 0}
    mode = getattr(config.research_scope, "methodology_screen", "off")
    if mode != "off":
        keep = "primary" if mode == "strict_primary" else "primary_and_unknown"
        doc_ids = {p.paper_id for p in doc_papers}
        on_topic, query_only = [], []
        for p in merged:
            (on_topic if p.paper_id in doc_ids else query_only).append(p)
        query_only, design_counts = screen(query_only, keep=keep)
        dropped = len(query_only)
        merged = on_topic + query_only
        _log.info(
            f"ingest: methodology_screen={mode} -> kept {len(query_only)}/{dropped} "
            f"query papers "
            f"(primary={design_counts['primary']}, "
            f"documentary={design_counts['documentary']}, "
            f"unknown={design_counts['unknown']}); "
            f"{len(on_topic)} explicit seed papers exempt",
        )

    # Mark the documents the user named so later stages (core ranking after
    # expand) keep them first.
    seed_ids = _mark_explicit_seeds(merged, doc_papers)

    # Ingest is bounded by the graph size; the LLM core is picked after expand.
    budget = config.research_scope.graph_cap
    if budget and len(merged) > budget:
        verdicts = {p.paper_id: classify(p) for p in merged}
        before = len(merged)
        merged = trim_to_budget(merged, limit=budget, seed_ids=seed_ids, verdicts=verdicts)
        _log.info(
            f"ingest: graph cap={budget} -> trimmed {before} to {len(merged)} "
            f"(explicit seeds retained: {len(seed_ids)})"
        )

    _reset_expand(out_dir)
    papers_path = out_dir / "papers.json"
    summary_path = out_dir / "ingest_summary.json"
    # Atomic writes via tmp + fsync + os.replace. Survives SIGKILL /
    # OOM / disk-full mid-write: papers.json either stays intact or
    # does not exist; the worst case is a stranded .tmp file alongside.
    atomic_write_text(
        papers_path,
        json.dumps([p.model_dump(mode="json") for p in merged], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if config.outputs.save_lmdb:
        write_papers_kv(out_dir / "papers.lmdb", merged)
    atomic_write_text(
        summary_path,
        json.dumps(
            {
                "schema_version": "1.0.0",
                "seed_count": len(config.seed_inputs),
                "raw_paper_count": len(doc_papers) + len(query_papers),
                "merged_paper_count": len(merged),
                "max_total_papers": config.research_scope.max_total_papers,
                "max_graph_papers": budget,
                "providers": registry.names() if registry else [],
                "methodology_screen": mode,
                "design_counts": design_counts,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


__all__ = ["dispatch", "merge", "run_ingest", "backfill_abstracts", "trim_to_budget"]
