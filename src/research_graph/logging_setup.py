"""research_graph.logging_setup — JSON-structured logging configured once.

Every pipeline stage calls ``configure_logging(level, json=...)`` once at
startup (idempotent: re-configuring is a no-op). Log records are JSON
objects on stderr by default; set ``json=False`` for human-readable format.

The ``stage`` extra field is conventional — every stage emits
``logger.info("...", extra={"stage": "ingest"})`` so consumers can filter
the structured stream by stage.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """JSON line per record. Stable across Python versions."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # surface any structured `extra={...}` we attached
        for key, val in record.__dict__.items():
            if key in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                continue
            if key.startswith("_"):
                continue
            payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, json: bool = True) -> logging.Logger:
    """Configure the root logger once. Returns the root logger for convenience.

    Re-calling is safe — the existing handler is replaced, not stacked.
    """
    global _CONFIGURED
    root = logging.getLogger()
    # remove existing handlers we previously attached
    for h in list(root.handlers):
        if getattr(h, "_research_graph_owned", False):
            root.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler.setFormatter(_JsonFormatter() if json else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s :: %(message)s"
    ))
    handler._research_graph_owned = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Per-module logger. Lazy: returns whatever the root is configured with."""
    return logging.getLogger(name)
