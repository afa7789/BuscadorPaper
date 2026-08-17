"""research_graph.cache — sqlite-backed key/value cache with content-hash keys.

The cache is intentionally tiny: a single table ``cache`` keyed by SHA-256 of
the canonicalized input. Every API call, every LLM response, every extraction
result goes through here. Pipeline stages are restartable: a single provider
outage never forces re-ingestion of N papers.

Concurrency: WAL journal mode allows multiple readers + one writer. The CLI
is single-process so contention is theoretical; WAL just future-proofs it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

CacheStatus = Literal["ok", "partial", "failed"]


class Cache:
    """Thin wrapper around a sqlite3 cache.db file.

    Values are stored as JSON blobs; canonicalization (sorted keys, no
    whitespace) is applied at hash time so re-runs of identical inputs
    always hit.
    """

    def __init__(self, path: str | Path = "./cache.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                source TEXT,
                fetched_at REAL NOT NULL,
                value_json TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_status ON cache(status)"
        )

    # ---- key derivation --------------------------------------------------

    @staticmethod
    def hash_payload(payload: Any) -> str:
        """Stable SHA-256 of a JSON-serializable payload."""
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_text(*parts: str) -> str:
        """Convenience: hash free-text parts (joined by NUL)."""
        joined = "\x00".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    # ---- get / set / by_status -------------------------------------------

    def get(self, key: str) -> tuple[CacheStatus, Any] | None:
        row = self._conn.execute(
            "SELECT status, value_json FROM cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        status, value_json = row
        if value_json is None:
            return (status, None)
        try:
            return (status, json.loads(value_json))
        except json.JSONDecodeError:
            return (status, None)

    def set(
        self,
        key: str,
        value: Any,
        *,
        status: CacheStatus = "ok",
        source: str | None = None,
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False) if value is not None else None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO cache
                (cache_key, status, source, fetched_at, value_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, status, source, time.time(), payload),
        )

    def by_status(self, status: CacheStatus) -> list[tuple[str, str | None]]:
        return list(
            self._conn.execute(
                "SELECT cache_key, source FROM cache WHERE status = ?", (status,)
            )
        )

    def count(self, status: CacheStatus | None = None) -> int:
        if status is None:
            row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM cache WHERE status = ?", (status,)
            ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()

    # context-manager sugar
    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
