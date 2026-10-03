"""Tests for the dependency-free .env loader in research_graph.config."""

import os
from pathlib import Path

from research_graph.config import _load_dotenv, load_config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_plain_pairs(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    _load_dotenv(_write(tmp_path, "RG_TEST_A=alpha\nRG_TEST_B=beta\n"))
    assert os.environ["RG_TEST_A"] == "alpha"
    assert os.environ["RG_TEST_B"] == "beta"


def test_existing_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("RG_TEST_A", "from-shell")
    _load_dotenv(_write(tmp_path, "RG_TEST_A=from-file\n"))
    assert os.environ["RG_TEST_A"] == "from-shell"


def test_export_prefix_stripped(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    _load_dotenv(_write(tmp_path, "export RG_TEST_A=alpha\n"))
    assert os.environ["RG_TEST_A"] == "alpha"


def test_comments_and_blank_lines_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    _load_dotenv(_write(tmp_path, "# a comment\n\n   \nRG_TEST_A=alpha\n"))
    assert os.environ["RG_TEST_A"] == "alpha"


def test_quoted_values_unwrapped(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    monkeypatch.delenv("RG_TEST_B", raising=False)
    _load_dotenv(_write(tmp_path, "RG_TEST_A='single'\nRG_TEST_B=\"double\"\n"))
    assert os.environ["RG_TEST_A"] == "single"
    assert os.environ["RG_TEST_B"] == "double"


def test_inline_hash_not_treated_as_comment(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    _load_dotenv(_write(tmp_path, "RG_TEST_A=https://x.example/#frag\n"))
    assert os.environ["RG_TEST_A"] == "https://x.example/#frag"


def test_missing_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("RG_TEST_A", raising=False)
    _load_dotenv(tmp_path / "nope.env")  # must not raise
    assert "RG_TEST_A" not in os.environ


def test_load_config_populates_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RG_TEST_A", raising=False)
    (tmp_path / "config.yaml").write_text(
        'project:\n  name: t\nseed_inputs:\n  - type: doi\n    value: "10.1/x"\n',
        encoding="utf-8",
    )
    _write(tmp_path, "RG_TEST_A=alpha\n")
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.project.name == "t"
    assert os.environ["RG_TEST_A"] == "alpha"