"""research_graph.providers._atomic — atomic file write helper.

Saves JSON / JSONL to disk using the standard tmp-file + fsync + os.replace
trick. Survives SIGKILL / OOM / disk-full mid-write: the canonical file at
``path`` stays intact or does not exist; the worst case is a stranded
``.tmp`` file alongside.

Used by ingest (``papers.json``), the run-ledger, and the JSONL output
sink.
"""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    """Write ``payload`` to ``path`` atomically (tmp + fsync + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding=encoding) as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Same as ``atomic_write_text`` but for binary payloads (e.g. cache pkl)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
