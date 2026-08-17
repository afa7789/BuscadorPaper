"""research_graph.graph — assemble + export the typed graph."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from research_graph.config import Config
from research_graph.graph.build import assemble
from research_graph.graph.export import export_all
from research_graph.logging_setup import configure_logging
from research_graph.models import ExtractionRecord, Institution, Author
from research_graph.providers import get_default_registry


_log = logging.getLogger(__name__)


def run_build_graph(
    config: Config,
    *,
    no_llm: bool = False,
    continue_on_error: bool = True,
) -> int:
    """Assemble the graph from papers + extractions + (optional) authors/institutions."""
    configure_logging(config.project.log_level, json=True)
    out_dir = Path(config.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers_path = out_dir / "papers.json"
    extractions_path = out_dir / "extractions.json"
    if not papers_path.exists():
        _log.error("build-graph: papers.json not found; run `ingest` first")
        return 1

    try:
        papers_data = json.loads(papers_path.read_text())
        from research_graph.models import Paper
        papers = [Paper.model_validate(p) for p in papers_data]
    except Exception as e:
        _log.error(f"build-graph: failed to read papers.json: {e}")
        return 1

    records: list[ExtractionRecord] = []
    if extractions_path.exists():
        try:
            recs_data = json.loads(extractions_path.read_text())
            records = [ExtractionRecord.model_validate(r) for r in recs_data]
        except Exception as e:
            _log.warning(f"build-graph: failed to load extractions.json ({e}); continuing")

    # Synthesize Author / Institution nodes from paper metadata (v1: lightweight)
    authors_seen: dict[str, Author] = {}
    institutions_seen: dict[str, Institution] = {}

    # Upgrade author nodes with OpenAlex canonical ids from people.json (when
    # the people stage ran first). Same for institutions.
    people_path = out_dir / "people.json"
    people_by_name: dict[str, dict] = {}
    if people_path.exists():
        try:
            for r in json.loads(people_path.read_text()):
                if r.get("author"):
                    people_by_name[r["author"].lower()] = r
        except Exception as e:
            _log.warning(f"build-graph: failed to load people.json ({e}); continuing")

    for p in papers:
        for a_name in p.authors:
            # Prefer OpenAlex canonical id if people.json resolved this name.
            ppl = people_by_name.get(a_name.lower(), {})
            if ppl.get("author_id"):
                aid = ppl["author_id"]
            else:
                aid = f"name:{a_name.lower()}"
            authors_seen.setdefault(aid, Author(author_id=aid, display_name=a_name))
        # Also seed institutions from people.json when an author was resolved.
        for r in people_by_name.values():
            if r.get("institution_id"):
                iid = r["institution_id"]
                institutions_seen.setdefault(
                    iid,
                    Institution(
                        institution_id=iid,
                        display_name=r.get("institution", "Unknown"),
                        ror=None,
                        country=None,
                    ),
                )
        # Plus the raw paper.affiliations list (legacy fallback)
        for aff in p.affiliations:
            iid = f"inst:{aff.lower().strip()}"
            institutions_seen.setdefault(iid, Institution(institution_id=iid, display_name=aff))

    graph = assemble(
        papers=papers,
        records=records,
        authors=list(authors_seen.values()),
        institutions=list(institutions_seen.values()),
    )

    paths = export_all(
        graph,
        out_dir,
        save_graphml=config.outputs.save_graphml,
        save_gexf=config.outputs.save_gexf,
        save_html_graph=config.outputs.save_html_graph,
        save_mermaid=config.outputs.save_mermaid,
        save_cytoscape_json=config.outputs.save_cytoscape_json,
    )
    _log.info(f"build-graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    for fmt, p in paths.items():
        _log.info(f"  {fmt}: {p}")
    return 0


__all__ = ["assemble", "export_all", "run_build_graph"]
