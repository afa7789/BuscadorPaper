"""Compatibility shim: re-export dedup.merge so expansion can call it
without an import cycle (expansion/__init__.py is loaded before dedup).
"""

from research_graph.ingestion.dedup import merge as merge_papers

__all__ = ["merge_papers"]
