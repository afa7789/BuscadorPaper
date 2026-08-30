"""research_graph.reports.html — self-contained output/index.html.

One file a non-technical user can double-click: every paper in a
searchable, sortable table with year, authors, venue, DOI link and a
link to the locally downloaded PDF when one exists. No CDN, no build
step; vanilla HTML+CSS+JS embedded below.
"""

from __future__ import annotations

import html as _html
import json
import os
from pathlib import Path

from research_graph.models import Paper


def _pdf_index(out_dir: Path) -> dict[str, str]:
    """Map paper_id -> pdf path relative to out_dir, from pdf_downloads.json."""
    path = out_dir / "pdf_downloads.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    index: dict[str, str] = {}
    for row in data.get("downloads", []):
        pid, pdf = row.get("paper_id"), row.get("pdf_path")
        if not pid or not pdf:
            continue
        try:
            index[pid] = os.path.relpath(Path(pdf).resolve(), out_dir.resolve())
        except ValueError:
            index[pid] = pdf
    return index


def _citation_count(paper: Paper) -> int | None:
    sp = paper.source_provenance if isinstance(paper.source_provenance, dict) else {}
    v = sp.get("citation_count")
    if isinstance(v, list):
        v = v[0] if v else None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _row(paper: Paper, pdfs: dict[str, str]) -> dict:
    return {
        "title": paper.title or paper.paper_id,
        "year": paper.year,
        "authors": ", ".join(paper.authors[:6]) + (" et al." if len(paper.authors) > 6 else ""),
        "venue": paper.venue or "",
        "doi": paper.doi or "",
        "citations": _citation_count(paper),
        "pdf": pdfs.get(paper.paper_id, ""),
        "url": (paper.urls[0] if paper.urls else ""),
    }


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__PROJECT__</title>
<style>
:root{--bg:#f6f7f8;--card:#fff;--ink:#1c262e;--muted:#5c6b75;--line:#d8dee3;--accent:#1b5a6d}
@media (prefers-color-scheme: dark){:root{--bg:#11181d;--card:#182228;--ink:#e4eaee;--muted:#96a5af;--line:#2b3a43;--accent:#63b6cc}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:2rem 1rem}
h1{font-size:1.6rem;margin:0 0 .25rem}
.sub{color:var(--muted);margin:0 0 1.25rem}
input{width:100%;box-sizing:border-box;padding:.6rem .8rem;font-size:1rem;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);margin-bottom:1rem}
.tblwrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:.5rem .7rem;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{cursor:pointer;user-select:none;white-space:nowrap;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}
th:hover{color:var(--accent)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.pdf{display:inline-block;padding:.05rem .45rem;border:1px solid var(--accent);border-radius:4px;font-size:.8rem;font-weight:600}
.count{color:var(--muted);font-size:.85rem;margin:.5rem 0 0}
</style></head><body><div class="wrap">
<h1>__PROJECT__</h1>
<p class="sub">__NPAPERS__ papers · __NPDFS__ PDFs baixados · gerado por BuscadorPaper</p>
<input id="q" type="search" placeholder="Filtrar por título, autor, venue, ano…" autofocus>
<div class="tblwrap"><table id="t">
<thead><tr>
<th data-k="title">Título</th><th data-k="year">Ano</th><th data-k="authors">Autores</th>
<th data-k="venue">Venue</th><th data-k="citations">Cit.</th><th>Links</th>
</tr></thead><tbody></tbody></table></div>
<p class="count" id="c"></p>
<script>
const DATA=__DATA__;
let rows=[...DATA],sortK="citations",sortDir=-1;
const tb=document.querySelector("#t tbody"),q=document.getElementById("q"),c=document.getElementById("c");
function esc(s){const d=document.createElement("span");d.textContent=s??"";return d.innerHTML}
function render(){
  const f=q.value.trim().toLowerCase();
  let v=rows.filter(r=>!f||[r.title,r.authors,r.venue,String(r.year??"")].join(" ").toLowerCase().includes(f));
  v.sort((a,b)=>{const x=a[sortK],y=b[sortK];
    if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
    return (typeof x=="number"? x-y : String(x).localeCompare(String(y)))*sortDir;});
  tb.innerHTML=v.map(r=>`<tr>
    <td>${esc(r.title)}</td><td class="n">${r.year??""}</td><td>${esc(r.authors)}</td>
    <td>${esc(r.venue)}</td><td class="n">${r.citations??""}</td>
    <td>${r.pdf?`<a class="pdf" href="${esc(r.pdf)}">PDF</a> `:""}${r.doi?`<a href="https://doi.org/${esc(r.doi)}">doi</a>`:(r.url?`<a href="${esc(r.url)}">link</a>`:"")}</td>
  </tr>`).join("");
  c.textContent=`${v.length} de ${rows.length} papers`;
}
q.addEventListener("input",render);
document.querySelectorAll("th[data-k]").forEach(th=>th.addEventListener("click",()=>{
  const k=th.dataset.k; sortDir=(k===sortK)?-sortDir:-1; sortK=k; render();
}));
render();
</script></div></body></html>
"""


def render_html(config, papers: list[Paper], out_dir: Path) -> Path:
    """Write output/index.html; returns its path."""
    pdfs = _pdf_index(out_dir)
    rows = [_row(p, pdfs) for p in papers]
    body = (
        _TEMPLATE
        .replace("__PROJECT__", _html.escape(getattr(config.project, "name", "papers")))
        .replace("__NPAPERS__", str(len(rows)))
        .replace("__NPDFS__", str(len(pdfs)))
        .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    )
    path = out_dir / "index.html"
    path.write_text(body, encoding="utf-8")
    return path
