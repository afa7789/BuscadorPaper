"""research_graph.providers._retry — retry policy with jitter.

Single place that defines backoff, max attempts, and what counts as a
retryable error. Used by provider HTTP calls; not yet wired into sync callers
(see ``_atomic`` for the sidecar helpers in the same family).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

import httpx


_log = logging.getLogger(__name__)


_DEFAULT_RETRY_ON: frozenset[int] = frozenset({429, 502, 503, 504})


def is_retryable(exc: BaseException, *, retry_on_status: frozenset[int] = _DEFAULT_RETRY_ON) -> bool:
    """True iff ``exc`` is a transient HTTP/transport error worth retrying."""
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in retry_on_status
    return False


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: bool = True
    retry_on_status: frozenset[int] = _DEFAULT_RETRY_ON

    def delay_for(self, attempt: int) -> float:
        d = min(self.max_delay, self.base_delay * (2 ** attempt))
        if self.jitter:
            # full jitter per RFC 9110
            d = random.uniform(0, d)
        return d


def default_policy() -> RetryPolicy:
    """Conservative default used when a provider does not override."""
    return RetryPolicy()


def retry_sync(fn, *, policy: RetryPolicy | None = None) -> httpx.Response | None:
    """Run ``fn()`` under ``policy`` until success or exhaustion.

    ``fn`` is a zero-arg callable returning an ``httpx.Response``. On retry-
    eligible failures (transport errors or 429/502/503/504), sleeps with
    jitter and retries. Returns the successful response, or ``None`` if all
    attempts failed (caller inspects ``_retries_attempted`` via logging).
    """
    pol = policy or default_policy()
    last_exc: BaseException | None = None
    for attempt in range(pol.max_retries + 1):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001
            if not is_retryable(exc, retry_on_status=pol.retry_on_status):
                raise
            last_exc = exc
            if attempt >= pol.max_retries:
                break
            sleep_for = pol.delay_for(attempt)
            _log.warning(
                "retryable error (attempt %d/%d), sleeping %.3fs",
                attempt + 1, pol.max_retries + 1, sleep_for,
                exc_info=False,
            )
            import time as _t
            _t.sleep(sleep_for)
    assert last_exc is not None
    _log.error("all %d retries failed: %r", pol.max_retries + 1, last_exc)
    return None
