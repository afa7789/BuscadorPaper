"""research_graph.llm — LLM provider abstraction.

Concrete providers (OpenAI-compatible) live alongside this. Tests can stub
providers with any object that satisfies the LLMProvider Protocol.
"""

from __future__ import annotations

from research_graph.llm.base import LLMProvider, LLMResult, Message
from research_graph.llm.openai_compatible import OpenAICompatibleProvider

__all__ = ["LLMProvider", "LLMResult", "Message", "OpenAICompatibleProvider"]


def build_default_provider(config) -> "OpenAICompatibleProvider":
    """Build the configured LLM provider from a Config instance.

    Looks up api_key and base_url via env var names specified in config.llm.
    """
    import os

    from research_graph.config import Config, lookup_env

    if isinstance(config, dict):
        # tolerate dict for tests; map to attributes
        llm_cfg = config.get("llm", {})
        base_url_env = llm_cfg.get("base_url_env", "MINIMAX_BASE_URL")
        api_key_env = llm_cfg.get("api_key_env", "MINIMAX_API_KEY")
        model = llm_cfg.get("model", "MiniMax-Text-01")
    else:
        base_url_env = config.llm.base_url_env
        api_key_env = config.llm.api_key_env
        model = config.llm.model

    base_url = lookup_env(base_url_env, required=True) or ""
    api_key = lookup_env(api_key_env, required=True) or ""
    return OpenAICompatibleProvider(api_key=api_key, base_url=base_url, model=model)
