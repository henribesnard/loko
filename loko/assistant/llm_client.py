"""LOKO Assistant — LLM client wrapper.

Reuses the bot's configured LLM provider (platform or custom)
via ``build_llm_provider`` and calls ``complete_chat()`` (non-streaming).
"""

from __future__ import annotations

import logging

from loko.bot.llm import build_llm_provider
from loko.bot.models import BotConfig

logger = logging.getLogger(__name__)


async def call_assistant_llm(
    bot_id: str,
    config: BotConfig,
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
) -> tuple[str, dict[str, int]]:
    """Call the LLM and return (response_text, usage_dict).

    Raises
    ------
    LLMProviderError
        When the provider is unavailable or returns an error.
    """
    provider = build_llm_provider(bot_id, config.llm)
    response = await provider.complete_chat(
        messages,
        max_tokens=max_tokens,
    )
    usage = provider.get_last_usage() or {}
    return response, usage
