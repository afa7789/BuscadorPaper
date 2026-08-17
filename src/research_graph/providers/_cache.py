"""research_graph.providers._cache — content-addressed disk cache for ProviderResult.

Cache key = sha256(provider | endpoint | params_json | version_tag).
Atomic write via tmp + ``os.replace``. TTL via per-file mtime.

Bumping ``_VERSION_TAG`` invalidates everything; use this when the Provider
shape changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any

from research_graph.models import ProviderResult


_log = logging.getLogger(__name__)


_VERSION_TAG = "v1"


class ProviderCache:
    """Disk-backed cache for provider responses."""

    def __init__(self, root: Path, *, ttl_seconds: float = 7 * 24 * 3600) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds

    def _key(self, provider: str, endpoint: str, params: dict[str, Any]) -> Path:
        h = hashlib.sha256()
        h.update(_VERSION_TAG.encode())
        for piece in (provider, endpoint, json.dumps(params, sort_keys=True, default=str)):
            h.update(b"|")
            h.update(piece.encode())
        digest = h.hexdigest()
        d = self._root / digest[:2] / digest[2:4]
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{digest}.pkl"

    def get(self, provider: str, endpoint: str, params: dict[str, Any]) -> ProviderResult | None:
        path = self._key(provider, endpoint, params)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._ttl:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
            if isinstance(obj, ProviderResult):
                return obj
        except Exception as e:  # corrupted cache entry
            _log.warning("cache read failed: %s", e)
            return None
        return None

    def set(
        self,
        provider: str,
        endpoint: str,
        params: dict[str, Any],
        result: ProviderResult,
    ) -> None:
        path = self._key(provider, endpoint, params)
        try:
            payload = pickle.dumps(result)
        except Exception as e:  # noqa: BLE001
            _log.warning("cache pickle failed: %s", e)
            return
        tmp = path.with_suffix(".pkl.tmp")
        try:
            with tmp.open("wb") as f:
                f.write(payload)
                f.flush()
                import os
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            _log.warning("cache write failed: %s", e)
