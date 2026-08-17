"""research_graph.providers._breaker — per-provider circuit breaker.

State machine CLOSED -> OPEN -> HALF_OPEN. Used by the ProviderRegistry to
isolate a flaky provider so a 5-minute OpenAlex outage doesn't burn the
whole run's timeout budget.

This is in-process state. A future PR can swap the counters for a sqlite
backend so workers see the same state — out of scope for the v1 polish.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from research_graph.models import ProviderResult


_BreakerStatus = str  # "ok" | "open" | "half_open"


@dataclass
class BreakerState:
    """Track consecutive failures for one provider.

    After ``failure_threshold`` consecutive failures the breaker opens
    for ``recovery_seconds``, during which the Resolver skips the provider.
    A single probe is admitted after recovery; success closes it, failure
    re-opens it.
    """

    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    _consecutive_failures: int = 0
    _opened_at_monotonic: float | None = None
    _half_open_in_flight: bool = False
    last_error: str | None = None

    def is_open(self) -> bool:
        """True when calls should be skipped (breaker is OPEN and probe window
        has not yet elapsed). Admitting a probe flips the state to half-open.
        """
        if self._opened_at_monotonic is None:
            return False
        if time.monotonic() - self._opened_at_monotonic >= self.recovery_seconds:
            self._half_open_in_flight = True
            return False
        return True

    def record(self, result: ProviderResult) -> None:
        if result.status == "ok":
            self._consecutive_failures = 0
            self._opened_at_monotonic = None
            self._half_open_in_flight = False
            self.last_error = None
            return
        self._consecutive_failures += 1
        self.last_error = result.error
        if self._half_open_in_flight:
            # Probe failed — re-open with a fresh TTL.
            self._opened_at_monotonic = time.monotonic()
            self._half_open_in_flight = False
            return
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at_monotonic = time.monotonic()

    def snapshot(self) -> _BreakerStatus:
        """Public health status, surfaced via ``registry.health()``."""
        if self._opened_at_monotonic is None:
            return "ok"
        if time.monotonic() - self._opened_at_monotonic >= self.recovery_seconds:
            return "half_open"
        return "open"
