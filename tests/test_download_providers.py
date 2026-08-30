"""Tests for scidb + unpaywall providers, registry gating, and html report."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from research_graph.config import Config
from research_graph.models import Paper
from research_graph.providers import get_default_registry
from research_graph.providers.scidb import SciDBProvider
from research_graph.providers.unpaywall import UnpaywallProvider


def _cfg(tmp_path: Path, enable: bool = True) -> Config:
    return Config.model_validate({
        "project": {"name": "t", "output_dir": str(tmp_path / "out"),
                    "cache_dir": str(tmp_path / "cache")},
        "seed_inputs": [{"type": "doi", "value": "10.1/x"}],
        "outputs": {"enable_pdf_download": enable,
                    "pdf_download_providers": ["openalex", "unpaywall", "scidb", "scihub", "annas"]},
    })


PDF = b"%PDF-1.5" + b"x" * 2048


# ---------- scidb ----------

def _scidb(tmp_path: Path, cfg: Config) -> SciDBProvider:
    p = SciDBProvider(cfg, cache_dir=tmp_path / "cache" / "scidb")
    p._min_interval = 0.0
    return p


def test_scidb_direct_pdf(tmp_path):
    p = _scidb(tmp_path, _cfg(tmp_path))
    with patch("research_graph.providers.scidb._http_get",
               return_value=(200, PDF, {"content-type": "application/pdf"})):
        r = p.fetch_by_doi("10.1145/3543507.3583217")
    assert r.status == "ok"
    assert Path(r.data["pdf_path"]).exists()
    # cache hit on second call, no HTTP
    r2 = p.fetch_by_doi("10.1145/3543507.3583217")
    assert r2.status == "ok" and r2.data["cached"] is True


def test_scidb_html_with_pdf_link(tmp_path):
    p = _scidb(tmp_path, _cfg(tmp_path))
    html = b'<html><a href="/files/paper.pdf">download</a></html>'
    calls = iter([
        (200, html, {"content-type": "text/html"}),
        (200, PDF, {"content-type": "application/pdf"}),
    ])
    with patch("research_graph.providers.scidb._http_get", side_effect=lambda *a, **k: next(calls)):
        r = p.fetch_by_doi("10.1/abc")
    assert r.status == "ok" and r.data["size_bytes"] > 1024


def test_scidb_ddos_guard_fails_with_instructions(tmp_path):
    p = _scidb(tmp_path, _cfg(tmp_path))
    challenge = b"<html><title>DDoS-Guard</title></html>"
    with patch("research_graph.providers.scidb._http_get",
               return_value=(403, challenge, {"content-type": "text/html"})):
        r = p.fetch_by_doi("10.1/blocked")
    assert r.status == "failed"
    assert "AA_COOKIES" in (r.error or "")


def test_scidb_opt_in(tmp_path):
    p = _scidb(tmp_path, _cfg(tmp_path, enable=False))
    assert p.fetch_by_doi("10.1/x").status == "failed"


# ---------- unpaywall ----------

def test_unpaywall_downloads_best_oa(tmp_path, monkeypatch):
    monkeypatch.setenv("UNPAYWALL_EMAIL", "t@t.com")
    p = UnpaywallProvider(_cfg(tmp_path), cache_dir=tmp_path / "cache" / "unpaywall")
    p._min_interval = 0.0
    p._email = "t@t.com"
    api = MagicMock(status_code=200)
    api.json.return_value = {"best_oa_location": {"url_for_pdf": "https://x/p.pdf"}}
    pdf = MagicMock(status_code=200, content=PDF, headers={"content-type": "application/pdf"})
    p._client = MagicMock(get=MagicMock(side_effect=[api, pdf]))
    r = p.fetch_by_doi("10.1/oa")
    assert r.status == "ok" and Path(r.data["pdf_path"]).exists()


def test_unpaywall_no_oa(tmp_path):
    p = UnpaywallProvider(_cfg(tmp_path), cache_dir=tmp_path / "cache" / "unpaywall")
    p._min_interval = 0.0
    p._email = "t@t.com"
    api = MagicMock(status_code=200)
    api.json.return_value = {"best_oa_location": None, "oa_locations": []}
    p._client = MagicMock(get=MagicMock(return_value=api))
    assert p.fetch_by_doi("10.1/closed").status == "failed"


# ---------- registry gating ----------

def test_registry_includes_download_providers_when_enabled(tmp_path):
    reg = get_default_registry(_cfg(tmp_path))
    for name in ("unpaywall", "scidb", "scihub", "annas", "openalex_pdf"):
        assert reg.get(name) is not None, name


def test_registry_excludes_download_providers_when_disabled(tmp_path):
    reg = get_default_registry(_cfg(tmp_path, enable=False))
    assert reg.get("scidb") is None
    assert reg.get("unpaywall") is None


def test_download_providers_enabled_flag_reads_outputs(tmp_path):
    """Regression: openalex_pdf/annas read config.search (wrong) -> always dead."""
    from research_graph.providers.annas import AnnasArchiveProvider
    from research_graph.providers.openalex_pdf import OpenAlexPdfProvider
    cfg = _cfg(tmp_path)
    assert AnnasArchiveProvider(cfg, cache_dir=tmp_path / "c1").enabled
    assert OpenAlexPdfProvider(cfg).enabled
    assert SciDBProvider(cfg, cache_dir=tmp_path / "c2").enabled


# ---------- html report ----------

def test_render_html(tmp_path):
    from research_graph.reports.html import render_html
    cfg = _cfg(tmp_path)
    out = Path(cfg.project.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = tmp_path / "cache" / "scidb" / "a.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(PDF)
    (out / "pdf_downloads.json").write_text(json.dumps(
        {"downloads": [{"paper_id": "p1", "pdf_path": str(pdf)}]}))
    papers = [
        Paper(paper_id="p1", title="Zswap", year=2022, doi="10.1/zswap",
              authors=["A", "B"]),
        Paper(paper_id="p2", title="Tornado <script>", year=2019, authors=[]),
    ]
    path = render_html(cfg, papers, out)
    body = path.read_text()
    assert path.name == "index.html"
    assert "Zswap" in body and "10.1/zswap" in body
    assert "<script>x" not in body  # escaped via json.dumps
    assert "a.pdf" in body  # relative pdf link present
