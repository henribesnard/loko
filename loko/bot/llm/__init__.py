"""LOKO Bot — LLM provider package.

Factory function to build LLM providers from environment or per-bot
configuration (Lot LLM §6.7).

Provider resolution:
1. config.llm.provider_source == "custom" → per-bot provider (BYO key)
2. Otherwise → platform provider from LOKO_LLM_* env vars (legacy)
"""

from __future__ import annotations

import logging
import os

from loko.bot.errors import ComponentUnavailableError

logger = logging.getLogger(__name__)


def build_llm_provider(bot_id: str, llm_config=None):
    """Build an LLM provider for a bot.

    Parameters
    ----------
    bot_id : str
        Bot identifier (for error messages and logging).
    llm_config : BotLLMConfig | None
        Per-bot LLM config. If None or provider_source=="platform",
        falls back to environment variables (legacy behavior).

    Returns
    -------
    LLMProvider
        An instance satisfying the ``LLMProvider`` protocol.

    Raises
    ------
    ComponentUnavailableError
        When required configuration is missing.
    """
    # --- Custom per-bot provider (Lot LLM) ---
    if llm_config is not None and llm_config.provider_source == "custom":
        return _build_custom_provider(bot_id, llm_config)

    # --- Platform provider (env vars, legacy) ---
    return _build_platform_provider(bot_id)


def _build_custom_provider(bot_id: str, llm_config):
    """Build a provider from per-bot BYO configuration."""
    from loko.bot.llm.openai_compat import OpenAICompatProvider

    base_url = llm_config.base_url
    model = llm_config.model

    if not base_url:
        raise ComponentUnavailableError(
            "llm",
            bot_id,
            "Custom LLM provider requires base_url.",
        )
    if not model:
        raise ComponentUnavailableError(
            "llm",
            bot_id,
            "Custom LLM provider requires model.",
        )
    if not llm_config.api_key_ref:
        raise ComponentUnavailableError(
            "llm",
            bot_id,
            "Custom LLM provider requires an API key. "
            "Use PUT /api/bot/{bot_id}/llm to set one.",
        )

    # SSRF validation + DNS rebinding protection on base_url
    from loko.security.ssrf import validate_url, resolve_and_pin, SSRFError

    try:
        validate_url(base_url)
    except SSRFError as exc:
        raise ComponentUnavailableError(
            "llm",
            bot_id,
            f"base_url blocked by SSRF validation: {exc.reason}",
        ) from exc

    # DNS rebinding protection: pin the resolved IP (server mode only)
    pinned_url = base_url
    original_host = None
    if os.environ.get("LOKO_MODE", "desktop").lower() == "server":
        try:
            pinned_url, original_host = resolve_and_pin(base_url)
        except SSRFError as exc:
            raise ComponentUnavailableError(
                "llm",
                bot_id,
                f"base_url DNS resolution blocked: {exc.reason}",
            ) from exc

    # Resolve API key from secret store
    from loko.security.secret_store import get_secret_store

    try:
        api_key = get_secret_store().get(llm_config.api_key_ref)
    except (KeyError, RuntimeError) as exc:
        raise ComponentUnavailableError(
            "llm",
            bot_id,
            f"Failed to resolve API key: {exc}",
        ) from exc

    logger.info(
        "Building custom LLM provider for bot %s: base_url=%s model=%s",
        bot_id,
        base_url,
        model,
    )
    return OpenAICompatProvider(
        base_url=pinned_url,
        api_key=api_key,
        model=model,
        host_header=original_host,
        # V2: pass original URL for per-request DNS re-resolution
        original_url=base_url,
    )


def _build_platform_provider(bot_id: str):
    """Build a provider from platform environment variables (legacy)."""
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
                "llm",
                bot_id,
                "LOKO_LLM_BASE_URL is required for openai_compat provider.",
            )
        if not api_key:
            raise ComponentUnavailableError(
                "llm",
                bot_id,
                "LOKO_LLM_API_KEY is required for openai_compat provider.",
            )
        if not model:
            raise ComponentUnavailableError(
                "llm",
                bot_id,
                "LOKO_LLM_MODEL is required for openai_compat provider.",
            )

        from loko.bot.llm.openai_compat import OpenAICompatProvider

        logger.info(
            "Building OpenAI-compat LLM provider for bot %s: base_url=%s model=%s",
            bot_id,
            base_url,
            model,
        )
        return OpenAICompatProvider(base_url=base_url, api_key=api_key, model=model)

    # No provider configured
    raise ComponentUnavailableError(
        "llm",
        bot_id,
        "No LLM provider configured. "
        "Set LOKO_LLM_BASE_URL, LOKO_LLM_API_KEY, and LOKO_LLM_MODEL, "
        "or set LOKO_LLM_PROVIDER=openai_compat.",
    )
