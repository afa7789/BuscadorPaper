"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "cache.sqlite"


@pytest.fixture()
def example_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
project:
  name: test
  language: en
  output_dir: "./output"
  cache_dir: "./cache"
  log_level: INFO
seed_inputs:
  - type: doi
    value: "10.1234/test"
research_scope:
  max_hops: 1
  max_total_papers: 50
  min_relevance_score: 0.35
""",
        encoding="utf-8",
    )
    return cfg
