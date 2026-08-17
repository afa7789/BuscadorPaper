"""research_graph.config — load YAML config + merge env vars + Pydantic validate.

Pipeline entry points all consume a single ``Config`` instance, produced by
``load_config(path)``. The model mirrors the structure documented in
``config.example.yaml``; missing optional sections get safe defaults.

Environment-variable indirection is enforced for *secrets* (LLM API keys,
provider polite-pool emails, etc.). The Config model exposes only
*references* to env vars (``base_url_env``, ``api_key_env``); the actual
values are looked up at provider construction time so that secret rotation
between stages does not require re-instantiation of Config.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------- Pipeline-wide types ------------------------------------------------

class ProjectConfig(BaseModel):
    name: str
    language: str = "pt-BR"
    output_dir: str = "./output"
    cache_dir: str = "./cache"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class SeedInput(BaseModel):
    type: Literal["pdf", "doi", "url", "title", "tavily_query", "ddg_query", "crossref_query"]
    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("seed_input.value must not be empty")
        return v


class ResearchScope(BaseModel):
    seed_keywords: list[str] = Field(default_factory=list)
    include_domains: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    max_hops: int = 2
    max_papers_per_query: int = 50
    max_total_papers: int = 300
    years_from: int = 2015
    years_to: int = 2026
    min_relevance_score: float = 0.35

    @field_validator("max_hops")
    @classmethod
    def _max_hops_in_range(cls, v: int) -> int:
        if v < 0 or v > 5:
            raise ValueError("max_hops must be in [0, 5]")
        return v

    @field_validator("min_relevance_score")
    @classmethod
    def _score_in_unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("min_relevance_score must be in [0, 1]")
        return v


class SearchConfig(BaseModel):
    providers: list[str] = Field(
        default_factory=lambda: ["openalex", "semantic_scholar", "crossref", "arxiv"]
    )
    expand_by: list[str] = Field(
        default_factory=lambda: [
            "references", "citations", "similarity",
            "authors", "institutions", "keywords",
        ]
    )
    professor_search: bool = True
    university_search: bool = True
    official_page_verification: bool = True
    # Fetch full-text PDFs via Sci-Hub (DOI resolution). Optional, opt-in.
    # When true the provider is registered, but each call still respects
    # Sci-Hub mirrors availability. See providers/scihub.py for legal notes.
    enable_scihub: bool = False


class LLMConfig(BaseModel):
    provider: str = "openai_compatible"
    base_url_env: str = "MINIMAX_BASE_URL"
    api_key_env: str = "MINIMAX_API_KEY"
    model: str = "MiniMax-Text-01"
    fallback_models: list[str] = Field(default_factory=list)
    temperature: float = 0.1
    max_output_tokens: int = 4000
    concurrency: int = 4
    structured_output: bool = True
    cache_responses: bool = True


class OptionalLLMProvider(BaseModel):
    name: str
    base_url_env: str
    api_key_env: str
    model_env: str | None = None
    model: str | None = None


class AnalysisConfig(BaseModel):
    extract_abstract: bool = True
    extract_problem: bool = True
    extract_contribution: bool = True
    extract_methods: bool = True
    extract_datasets: bool = True
    extract_limitations: bool = True
    extract_future_work: bool = True
    extract_metrics: bool = True
    extract_authors: bool = True
    extract_affiliations: bool = True
    generate_project_ideas: bool = True
    generate_advisor_shortlist: bool = True


class OutputsConfig(BaseModel):
    """Output toggles + PDF download options.

    By default only ``save_json``, ``save_html_graph``, and
    ``save_markdown_report`` are enabled — the 3 forms most users actually
    open. The other formats are available; flip the flag to true if you
    need them.
    """

    # Output formats
    save_json: bool = True
    save_csv: bool = False
    save_graphml: bool = True   # used by analyze stage
    save_gexf: bool = False
    save_html_graph: bool = True
    save_markdown_report: bool = True
    save_mermaid: bool = False
    save_cytoscape_json: bool = False

    # PDF download (optional, off by default)
    enable_pdf_download: bool = False
    max_papers_to_download: int = 5
    pdf_download_providers: list[str] = Field(
        default_factory=lambda: ["openalex", "scihub", "annas"]
    )


class Config(BaseModel):
    project: ProjectConfig
    seed_inputs: list[SeedInput]
    research_scope: ResearchScope = ResearchScope()
    search: SearchConfig = SearchConfig()
    llm: LLMConfig = LLMConfig()
    optional_llm_providers: list[OptionalLLMProvider] = Field(default_factory=list)
    analysis: AnalysisConfig = AnalysisConfig()
    outputs: OutputsConfig = OutputsConfig()


# ---------- Loader -------------------------------------------------------------

def load_config(path: str | Path) -> Config:
    """Load + validate the YAML config at ``path``.

    Raises FileNotFoundError if the file does not exist, ValidationError on
    schema violations. Empty optional sections get defaults from the model
    definitions above.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"config file not found: {path}. "
            "Copy config.example.yaml to config.yaml and edit it."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping, got {type(raw).__name__}")
    return Config.model_validate(raw)


def lookup_env(name: str, *, default: str | None = None, required: bool = False) -> str | None:
    """Read an env var by name. ``required=True`` raises if missing.

    Used by LLM and provider constructors to resolve ``base_url_env`` /
    ``api_key_env`` references at call time, not at config-load time.
    """
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"required environment variable not set: {name}")
    return val
