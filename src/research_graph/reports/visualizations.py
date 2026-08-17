"""research_graph.reports.visualizations — embed pyvis HTML + Mermaid in the report."""

from __future__ import annotations

from pathlib import Path


def embed_visualizations(report_path: Path, graph_html_path: Path, mermaid_path: Path) -> None:
    """Append an appendix linking to the interactive HTML and embedding the Mermaid block."""
    appendix = ["\n## Appendix: Visualizations\n"]
    if graph_html_path.exists():
        appendix.append(f"- Interactive graph: `{graph_html_path}`")
    if mermaid_path.exists():
        appendix.append("\n### Mermaid\n")
        appendix.append("```mermaid")
        appendix.append(mermaid_path.read_text(encoding="utf-8"))
        appendix.append("```")
    with report_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(appendix))
