"""research_graph — local-first bibliometric mapping pipeline.

Public entry point lives in ``cli.py`` (registered as the ``research-graph``
console script in ``pyproject.toml``). All pipeline stages are exposed as
importable subpackages so a future web UI can compose them without going
through the CLI.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
