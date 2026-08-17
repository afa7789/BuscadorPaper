"""research_graph.providers — registry of academic data providers + fallback.

The registry holds a priority-ordered list of providers per the Config
``search.providers`` list. Concrete providers (arxiv, openalex, semantic_scholar,
crossref, tavily, ddg, scihub, annas, openalex_pdf, university_pages) are
instantiated on demand by name; tests can override the registry contents
without touching call sites.

Fallback (Resolver): for any query, walk providers in priority order,
returning the first ``ProviderResult(status="ok")`` or the first non-failed
result if all failed but data is partial. Each provider has a per-call
``BreakerState`` so a flaky upstream doesn't burn the run's timeout budget.

This module exports:
  - ProviderRegistry: holds provider instances + breaker state, O(1) lookup
  - get_default_registry(config): build a registry from a Config
  - Resolver: walks a registry honoring breaker state
  - registry.health(): dict[name -> "ok" | "open" | "half_open"]
"""

from __future__ import annotations

import logging
from typing import Callable

from research_graph.config import Config
from research_graph.models import ProviderResult

from research_graph.providers.base import AcademicProvider
from research_graph.providers._breaker import BreakerState


_log = logging.getLogger(__name__)


# Single source of truth: name -> (module, class, soft_fail).
# Soft-fail providers (e.g. tavily without TAVILY_API_KEY) raise RuntimeError
# during construction; we catch and downgrade to a warning instead of
# crashing the registry build.
_PROVIDER_TABLE: dict[str, tuple[str, str, bool]] = {}


def _register_provider(name: str, module: str, cls: str, *, soft_fail: bool = False) -> None:
    """Capture module+class for a provider; never imported eagerly."""
    _PROVIDER_TABLE[name] = (module, cls, soft_fail)


def _bootstrap_provider_table() -> None:
    if _PROVIDER_TABLE:
        return
    for name, mod, cls, soft in [
        ("openalex",          "research_graph.providers.openalex",          "OpenAlexProvider",          False),
        ("semantic_scholar",  "research_graph.providers.semantic_scholar", "SemanticScholarProvider",   False),
        ("crossref",          "research_graph.providers.crossref",          "CrossrefProvider",          False),
        ("arxiv",             "research_graph.providers.arxiv",             "ArxivProvider",             False),
        ("university_pages",  "research_graph.providers.university_pages",  "UniversityPagesProvider",  False),
        ("ddg",               "research_graph.providers.ddg",               "DDGProvider",               False),
        ("scihub",            "research_graph.providers.scihub",            "SciHubProvider",            False),
        ("annas",             "research_graph.providers.annas",             "AnnasArchiveProvider",       False),
        ("openalex_pdf",      "research_graph.providers.openalex_pdf",      "OpenAlexPdfProvider",        False),
        ("tavily",            "research_graph.providers.tavily",            "TavilyProvider",            True),
    ]:
        _register_provider(name, mod, cls, soft_fail=soft)


_bootstrap_provider_table()


class ProviderRegistry:
    """Priority-ordered registry with breaker state per provider.

    Insertion order IS priority order (lower index = tried first). The
    internal ``_by_name`` dict gives O(1) lookups for ``get()`` without
    changing the public priority semantics.
    """

    def __init__(self, providers: list[AcademicProvider] | None = None) -> None:
        # Preserve first occurrence (priority) when deduping by name.
        seen_names: set[str] = set()
        deduped: list[AcademicProvider] = []
        for p in (providers or []):
            if p.name not in seen_names:
                deduped.append(p)
                seen_names.add(p.name)
        self._providers: list[AcademicProvider] = deduped
        self._by_name: dict[str, AcademicProvider] = {p.name: p for p in deduped}
        self._breakers: dict[str, BreakerState] = {p.name: BreakerState() for p in deduped}

    def register(self, provider: AcademicProvider) -> None:
        if provider.name in self._by_name:
            return  # idempotent re-register
        self._providers.append(provider)
        self._by_name[provider.name] = provider
        self._breakers[provider.name] = BreakerState()

    def get(self, name: str) -> AcademicProvider | None:
        return self._by_name.get(name)

    def breaker(self, name: str) -> BreakerState | None:
        return self._breakers.get(name)

    def all(self) -> list[AcademicProvider]:
        return list(self._providers)

    def names(self) -> list[str]:
        return [p.name for p in self._providers]

    def health(self) -> dict[str, str]:
        """Snapshot of every provider's breaker state, for ops dashboards."""
        return {name: b.snapshot() for name, b in self._breakers.items()}


def _build_provider(name: str, config: Config) -> AcademicProvider | None:
    """Lazy-instantiate the provider by name. Returns None on hard failure.

    Soft-fail providers (tavily when TAVILY_API_KEY is unset) raise
    RuntimeError during construction; we catch and downgrade to a warning
    rather than crashing the registry build.
    """
    entry = _PROVIDER_TABLE.get(name)
    if entry is None:
        _log.debug("unknown provider name %r", name)
        return None
    module_path, class_name, soft_fail = entry
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)(config)
    except Exception as e:  # noqa: BLE001
        if soft_fail:
            _log.warning(
                "%s provider skipped: %s",
                name,
                str(e) or "missing required env var (set TAVILY_API_KEY)",
            )
        else:
            _log.error(
                "provider %r failed to build: %s",
                name,
                e,
            )
        return None


def get_default_registry(config: Config) -> ProviderRegistry:
    """Build a registry ordered as in ``config.search.providers``.

    Unknown names are logged at DEBUG. Build failures (e.g. missing
    ``TAVILY_API_KEY``) are logged at WARNING and the provider is skipped.
    Duplicates are de-duplicated by name, preserving first occurrence.
    """
    providers: list[AcademicProvider] = []
    seen_names: set[str] = set()
    for name in config.search.providers:
        p = _build_provider(name, config)
        if p is None:
            continue
        if p.name in seen_names:
            _log.debug("duplicate provider %r ignored", p.name)
            continue
        providers.append(p)
        seen_names.add(p.name)
    if not providers:
        _log.warning(
            "registry built with zero providers (config.search.providers=%s)",
            list(config.search.providers),
        )
    return ProviderRegistry(providers)


class Resolver:
    """Walks a registry in priority order, returning the best available result.

    A ProviderResult is "ok" iff ``status == "ok"``.
    A ProviderResult is "partial" iff ``status == "partial"`` with non-None data.
    A ProviderResult is "failed" iff ``status == "failed"`` or ``data is None``.

    The Resolver also maintains the per-provider BreakerState: a provider
    whose breaker is OPEN (and probe window hasn't elapsed) is skipped,
    so a 5-minute OpenAlex outage doesn't stall every subsequent attempt.

    On a fully-failed walk, returns a synthetic failed result carrying the
    last error seen so callers have something to log.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def resolve(self, fn: Callable[[AcademicProvider], ProviderResult]) -> ProviderResult:
        """Call ``fn(provider)`` for each registered provider in order.

        Skips providers whose breaker is OPEN (probe window not elapsed).
        Returns the first OK, else the first partial, else a synthetic
        failed result.
        """
        last_failed: ProviderResult | None = None
        first_partial: ProviderResult | None = None
        for provider in self._registry.all():
            breaker = self._registry.breaker(provider.name)
            if breaker is not None and breaker.is_open():
                _log.debug("skipping provider %r (breaker open)", provider.name)
                continue
            try:
                result = fn(provider)
            except Exception as e:  # noqa: BLE001
                _log.warning("resolver: provider %r raised: %s", provider.name, e)
                from research_graph.models import ProviderResult as _PR
                result = _PR(status="failed", error=str(e), source=provider.name)
            # Update breaker AFTER the call. One record per attempt (not
            # double-counted at every collect_*_callsite).
            if breaker is not None:
                breaker.record(result)
            if result.status == "ok":
                return result
            if (
                result.status == "partial"
                and result.data is not None
                and first_partial is None
            ):
                first_partial = result
            if result.status == "failed":
                last_failed = result
        if first_partial is not None:
            return first_partial
        if last_failed is not None:
            return last_failed
        return ProviderResult(
            status="failed",
            error="no providers registered",
            source="resolver",
        )
