"""research_graph CLI — argparse root with 7 subcommands + `run`.

Each stage is idempotent, cache-keyed, and restartable. ``run`` chains all
stages with per-stage error tolerance.

Usage:
    research-graph ingest --config config.yaml
    research-graph expand --config config.yaml
    research-graph extract --config config.yaml
    research-graph build-graph --config config.yaml
    research-graph analyze --config config.yaml
    research-graph synthesize --config config.yaml
    research-graph people --config config.yaml
    research-graph generate-report --config config.yaml
    research-graph run --config config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research_graph import __version__


_log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research-graph",
        description="Local-first bibliometric mapping: seed papers -> typed "
                    "knowledge graph -> markdown report with LLM-derived "
                    "research project proposals.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--config", type=Path, default=Path("config.yaml"),
                        help="Path to config.yaml (default: ./config.yaml).")
        sp.add_argument("--no-llm", action="store_true",
                        help="Skip LLM stages (extract synthesis project_ideas).")
        sp.add_argument("--continue-on-error", action="store_true", default=True,
                        help="Continue past stage failures (default: true).")
        return sp

    add("ingest", "Resolve seed_inputs into deduplicated papers.")
    add("expand", "Walk citations, similarity, and authors up to max_hops.")
    add("extract", "Structured LLM extraction of problem, contribution, claims, etc.")
    add("build-graph", "Construct the typed heterogeneous graph.")
    add("analyze", "Centrality, communities, repeated limitations/future works.")
    add("synthesize", "LLM executive summary, communities, project ideas.")
    add("people", "Collect affiliation evidence for in-scope authors.")
    add("generate-report", "Synthesize + render Markdown report.")
    add("scihub-fetch", "Download full-text PDFs for known DOIs via Sci-Hub (opt-in).")
    add("download-pdfs", "Try to download up to N full-text PDFs (openalex_pdf > scihub > annas).")
    add("run", "Full pipeline (ingest -> ... -> generate-report).")
    return p


def _run_download_pdfs(cfg, *, no_llm: bool = False, continue_on_error: bool = True) -> int:
    """Try downloading full-text PDFs for papers in output/papers.json.

    Strategy: walk the priority list of pdf_download_providers; for each
    paper, try the first provider that has a relevant entry (openalex_pdf
    needs paper.source_provenance.openalex_pdf_url; scihub needs DOI;
    annas does free-text search). Stop once ``max_papers_to_download``
    papers have been downloaded or all candidates exhausted.
    """
    import json
    import logging
    from pathlib import Path

    from research_graph.logging_setup import configure_logging
    from research_graph.models import Paper
    from research_graph.providers import get_default_registry

    configure_logging(cfg.project.log_level, json=True)
    log = logging.getLogger(__name__)

    if not getattr(cfg.outputs, "enable_pdf_download", False):
        log.warning("download-pdfs: enable_pdf_download is false in config.yaml; exiting cleanly.")
        return 0

    registry = get_default_registry(cfg)
    providers_cfg = list(cfg.outputs.pdf_download_providers)
    log.info(f"download-pdfs: provider order = {providers_cfg}")

    out_dir = Path(cfg.project.output_dir)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        log.warning(f"download-pdfs: papers.json not found at {papers_path}; run `ingest` first")
        return 1

    papers_data = json.loads(papers_path.read_text())
    papers = [Paper.model_validate(p) for p in papers_data]
    log.info(f"download-pdfs: {len(papers)} papers loaded")

    max_n = int(getattr(cfg.outputs, "max_papers_to_download", 5))
    downloaded = 0
    failures: list[dict] = []

    # Iterate papers in declaration order; honor max_n
    queue = list(papers)[:max_n * 3]  # over-fetch candidates; we stop early on success
    log.info(f"download-pdfs: trying up to {max_n} papers from {len(queue)} candidates")

    for paper in queue:
        if downloaded >= max_n:
            break
        sp = paper.source_provenance or {}
        if not isinstance(sp, dict):
            sp = {}
        # 1) openalex_pdf if URL already in provenance
        if "openalex" in providers_cfg and "openalex_pdf_url" in sp:
            prov = registry.get("openalex_pdf")
            if prov and getattr(prov, "enabled", False):
                prov.enable()
                r = prov.download_paper_pdf(paper)
                if r.status == "ok":
                    downloaded += 1
                    log.info(f"download-pdfs: ok [{downloaded}/{max_n}] {paper.paper_id} ({paper.title[:60]})")
                    continue
                log.debug(f"download-pdfs: openalex_pdf failed for {paper.paper_id}: {r.error}")
        # 2) scihub if DOI available
        if "scihub" in providers_cfg and paper.doi:
            prov = registry.get("scihub")
            if prov:
                prov.enable()
                r = prov.fetch_by_doi(paper.doi)
                if r.status == "ok":
                    downloaded += 1
                    log.info(f"download-pdfs: ok [{downloaded}/{max_n}] (scihub) {paper.paper_id}")
                    continue
                log.debug(f"download-pdfs: scihub failed for {paper.paper_id}: {r.error}")
        # 3) annas if available
        if "annas" in providers_cfg:
            prov = registry.get("annas")
            if prov and getattr(prov, "enabled", False):
                prov.enable()
                hits = prov.fetch_by_query(paper.title or paper.paper_id, limit=2)
                if hits.status == "ok" and isinstance(hits.data, list) and hits.data:
                    md5 = hits.data[0][0]
                    r = prov.download_md5(md5)
                    if r.status == "ok":
                        downloaded += 1
                        log.info(f"download-pdfs: ok [{downloaded}/{max_n}] (annas) {paper.paper_id}")
                        continue
                    log.debug(f"download-pdfs: annas failed for {paper.paper_id}: {r.error}")
        failures.append({"paper_id": paper.paper_id, "title": paper.title,
                         "reason": "no provider yielded a PDF"})

    summary_path = out_dir / "pdf_downloads.json"
    summary_path.write_text(json.dumps({
        "max_papers_to_download": max_n,
        "providers_tried": providers_cfg,
        "downloaded_count": downloaded,
        "failures_count": len(failures),
        "failures": failures,
    }, indent=2))
    log.info(f"download-pdfs: {downloaded}/{max_n} OK -> {summary_path}")
    return 0


def _run_scihub(cfg, *, no_llm: bool = False, continue_on_error: bool = True) -> int:
    """Fetch full-text PDFs for known DOIs via Sci-Hub (opt-in)."""
    import json
    import logging
    from pathlib import Path

    from research_graph.logging_setup import configure_logging
    from research_graph.providers.scihub import SciHubProvider
    from research_graph.providers import get_default_registry

    configure_logging(cfg.project.log_level, json=True)
    log = logging.getLogger(__name__)

    if not getattr(getattr(cfg, "search", None), "enable_scihub", False):
        log.warning("scihub-fetch: enable_scihub is false in config.yaml — exiting cleanly.")
        return 0

    scihub = SciHubProvider(cfg)
    scihub.enable()
    log.info("scihub-fetch: provider enabled with %d mirrors", len(scihub._mirrors))

    out_dir = Path(cfg.project.output_dir)
    papers_path = out_dir / "papers.json"
    if not papers_path.exists():
        log.warning(f"scihub-fetch: papers.json not found at {papers_path}; run `ingest` first")
        return 1

    papers = json.loads(papers_path.read_text())
    dois = [p["doi"] for p in papers if p.get("doi")]
    log.info(f"scihub-fetch: {len(dois)} candidates with DOI")

    fetched = []
    failed = []
    for doi in dois:
        r = scihub.fetch_by_doi(doi)
        if r.status == "ok":
            fetched.append(r.data)
            log.info(f"scihub-fetch: OK  {doi} -> {r.data.get('pdf_path')} ({r.data.get('size_bytes')} bytes)")
        else:
            failed.append({"doi": doi, "error": r.error})
            log.warning(f"scihub-fetch: FAIL {doi}: {r.error}")

    summary_path = out_dir / "scihub_fetch.json"
    summary_path.write_text(
        json.dumps({
            "candidates": len(dois),
            "fetched_count": len(fetched),
            "failed_count": len(failed),
            "fetched": fetched,
            "failed": failed,
        }, indent=2),
    )
    log.info(f"scihub-fetch: {len(fetched)}/{len(dois)} OK -> {summary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    from research_graph.config import load_config
    try:
        cfg = load_config(args.config)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        print("hint: copy config.example.yaml to config.yaml first.", file=sys.stderr)
        return 2

    kwargs = dict(no_llm=args.no_llm, continue_on_error=args.continue_on_error)

    if args.command == "ingest":
        from research_graph.ingestion import run_ingest
        return run_ingest(cfg, **kwargs)
    if args.command == "expand":
        from research_graph.expansion import run_expand
        return run_expand(cfg, **kwargs)
    if args.command == "extract":
        from research_graph.extraction import run_extract
        return run_extract(cfg, **kwargs)
    if args.command == "build-graph":
        from research_graph.graph import run_build_graph
        return run_build_graph(cfg, **kwargs)
    if args.command == "analyze":
        from research_graph.analysis import run_analyze
        return run_analyze(cfg, **kwargs)
    if args.command == "synthesize":
        from research_graph.synthesis import run_synthesize
        return run_synthesize(cfg, **kwargs)
    if args.command == "people":
        from research_graph.people import run_people
        return run_people(cfg, **kwargs)
    if args.command == "generate-report":
        from research_graph.reports import run_generate_report
        return run_generate_report(cfg, **kwargs)
    if args.command == "scihub-fetch":
        return _run_scihub(cfg, **kwargs)
    if args.command == "download-pdfs":
        return _run_download_pdfs(cfg, **kwargs)
    if args.command == "run":
        from research_graph.ingestion import run_ingest
        from research_graph.expansion import run_expand
        from research_graph.extraction import run_extract
        from research_graph.graph import run_build_graph
        from research_graph.analysis import run_analyze
        from research_graph.synthesis import run_synthesize
        from research_graph.people import run_people
        from research_graph.reports import run_generate_report
        # Order matters: people BEFORE expand so author_ids are available for
        # author-based expansion; expand BEFORE build-graph so the graph reflects
        # the full paper neighborhood.
        stages = [
            ("ingest", run_ingest),
            ("people", run_people),
            ("expand", run_expand),
            ("extract", run_extract),
            ("build-graph", run_build_graph),
            ("analyze", run_analyze),
            ("synthesize", run_synthesize),
            ("generate-report", run_generate_report),
        ]
        last_rc = 0
        for name, fn in stages:
            print(f"[run] >>> {name}")
            rc = fn(cfg, **kwargs)
            last_rc = rc if rc != 0 else last_rc
            if rc != 0 and not args.continue_on_error:
                return rc
        return last_rc

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
