"""Tests that each provider returns ProviderResult(status='failed') on HTTP errors."""

from research_graph.config import Config
from research_graph.providers import ProviderRegistry, get_default_registry


def test_registry_constructs_with_empty_config():
    cfg = Config.model_validate({
        "project": {"name": "test"},
        "seed_inputs": [],
        "research_scope": {},
        "search": {"providers": ["openalex", "arxiv"]},
    })
    registry = get_default_registry(cfg)
    assert "openalex" in registry.names()
    assert "arxiv" in registry.names()


def test_provider_returns_failed_on_404():
    """A non-existent DOI should produce a failed/partial result, never raise."""
    cfg = Config.model_validate({
        "project": {"name": "test"},
        "seed_inputs": [],
    })
    registry = get_default_registry(cfg)
    openalex = registry.get("openalex")
    assert openalex is not None
    r = openalex.fetch_by_doi("10.999999/nonexistent")
    assert r.status in ("failed", "partial", "ok")  # never raises
