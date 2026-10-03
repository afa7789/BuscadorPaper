"""research_graph.expansion — bounded graph walk over references + citations + similarity + authors."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.config import Config
from research_graph.expansion.citations import ExpandState, expand_seeds
from research_graph.expansion.core import canonical_links, rank_core
from research_graph.expansion.dedup_compat import merge_papers
from research_graph.logging_setup import configure_logging
from research_graph.models import Paper
from research_graph.providers import get_default_registry
from research_graph.papers_kv import write_papers_kv


_log = logging.getLogger(__name__)


def run_expand(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Run the expand stage: walks citation graph from each seed paper."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        _log.error("expand: papers.json not found; run `ingest` first")
        return 1
    try:
        seeds = [Paper.model_validate(p) for p in json.loads(papers_path.read_text())]
    except Exception as e:
        _log.error(f"expand: failed to read papers.json: {e}")
        return 1

    try:
        registry = get_default_registry(config)
    except Exception as e:
        _log.error(f"expand: failed to build registry: {e}")
        if not continue_on_error:
            return 1
        return 1

    # Resume point + links from earlier runs; `ingest` deletes both to restart.
    state_path, links_path = out_dir / "expand_state.json", out_dir / "links.json"
    state = ExpandState.from_json(_read_json(state_path, {}))
    try:
        walked: list[dict] = _read_json(links_path, [])
        expanded = expand_seeds(
            seeds,
            registry,
            max_hops=config.research_scope.max_hops,
            max_total=config.research_scope.graph_cap,
            min_score=config.research_scope.min_relevance_score,
            expand_by=config.search.expand_by,
            links=walked,
            state=state,
        )
        merged = merge_papers(seeds + expanded)
        links = canonical_links(seeds + expanded, merged, walked)
        seed_ids = {p.paper_id for p in merged
                    if (p.source_provenance or {}).get("explicit_seed")}
        # Best-first: the core is the first max_total_papers of papers.json.
        merged = rank_core(merged, links, seed_ids)
        links_path.write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")
        state_path.write_text(json.dumps(state.to_json(), indent=2), encoding="utf-8")
        papers_path.write_text(
            json.dumps([p.model_dump(mode="json") for p in merged], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if config.outputs.save_lmdb:
            write_papers_kv(out_dir / "papers.lmdb", merged)
        _log.info(
            f"expand: {len(seeds)} seeds -> {len(merged)} papers, {len(links)} links; "
            f"core = first {config.research_scope.max_total_papers}; "
            f"hops so far {state.hops_done}, next frontier {len(state.frontier)}"
        )
        return 0
    except Exception as e:
        _log.error(f"expand failed: {e}")
        return 1 if not continue_on_error else 0


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as e:
        _log.warning(f"expand: ignoring unreadable {path.name}: {e}")
        return default


__all__ = ["ExpandState", "expand_seeds", "run_expand"]
