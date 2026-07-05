"""LOKO Bot — LLM provider package.

Factory function to build LLM providers from environment configuration.
"""

from __future__ import annotations

import logging
import os

from loko.bot.errors import ComponentUnavailableError

logger = logging.getLogger(__name__)


def build_llm_provider(bot_id: str):
    """Build an LLM provider from environment variables.

    Supported providers:
    - ``openai_compat`` (default when LOKO_LLM_BASE_URL is set):
      Any OpenAI-compatible endpoint (OpenAI, DeepSeek, Mistral, vLLM, Ollama).

    Required env vars for ``openai_compat``:
    - LOKO_LLM_BASE_URL — e.g. https://api.openai.com/v1
    - LOKO_LLM_API_KEY — bearer token
    - LOKO_LLM_MODEL — model identifier (e.g. gpt-4o-mini)

    Returns
    -------
    LLMProvider
        An instance satisfying the ``LLMProvider`` protocol.

    Raises
    ------
    ComponentUnavailableError
        When required env vars are missing.
    """
    provider_type = os.environ.get("LOKO_LLM_PROVIDER", "").lower()
    base_url = os.environ.get("LOKO_LLM_BASE_URL", "")
    api_key = os.environ.get("LOKO_LLM_API_KEY", "")
    model = os.environ.get("LOKO_LLM_MODEL", "")

    # Auto-detect: if base_url is set but provider is not, assume openai_compat
    if not provider_type and base_url:
        provider_type = "openai_compat"

    if provider_type == "openai_compat":
        if not base_url:
            raise ComponentUnavailableError(
                "llm", bot_id,
                "LOKO_LLM_BASE_URL is required for openai_compat provider.",
            )
        if not api_key:
            raise ComponentUnavailableError(
                "llm", bot_id,
                "LOKO_LLM_API_KEY is required for openai_compat provider.",
            )
        if not model:
            raise ComponentUnavailableError(
                "llm", bot_id,
                "LOKO_LLM_MODEL is required for openai_compat provider.",
            )

        from loko.bot.llm.openai_compat import OpenAICompatProvider

        logger.info(
            "Building OpenAI-compat LLM provider for bot %s: base_url=%s model=%s",
            bot_id, base_url, model,
        )
        return OpenAICompatProvider(base_url=base_url, api_key=api_key, model=model)

    # No provider configured
    raise ComponentUnavailableError(
        "llm", bot_id,
        "No LLM provider configured. "
        "Set LOKO_LLM_BASE_URL, LOKO_LLM_API_KEY, and LOKO_LLM_MODEL, "
        "or set LOKO_LLM_PROVIDER=openai_compat.",
    )
