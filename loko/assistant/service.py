"""LOKO Assistant — Service layer (orchestration).

Dispatches use-case requests to the appropriate prompt builder,
calls the LLM, parses the response, and returns proposals.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException

from loko.assistant.llm_client import call_assistant_llm
from loko.assistant.prompts import (
    build_a2_discriminate_prompt,
    build_a2_generate_prompt,
    build_a2_review_prompt,
)
from loko.assistant.proposals import (
    AssistantRequest,
    AssistantResponse,
    Proposal,
    SubMode,
    UseCase,
)
from loko.bot.models import BotConfig

logger = logging.getLogger(__name__)

# Regex to extract a JSON array from LLM output that may be wrapped in markdown
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """Extract and parse a JSON array from LLM output.

    Handles common LLM quirks: markdown fences, preamble text, etc.
    """
    # Try direct parse first
    text = text.strip()
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Strip markdown fences
    if "```" in text:
        # Extract content between fences
        parts = text.split("```")
        for part in parts[1::2]:  # odd indices = inside fences
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    # Regex fallback: find first JSON array
    match = _JSON_ARRAY_RE.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse JSON array from LLM response: %s", text[:200])
    return []


def _normalize(text: str) -> str:
    """Normalize text for dedup comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _deduplicate(
    proposals: list[dict[str, Any]],
    existing: list[str],
) -> list[dict[str, Any]]:
    """Remove proposals that duplicate existing examples."""
    existing_normalized = {_normalize(e) for e in existing}
    seen: set[str] = set()
    result = []
    for p in proposals:
        content = p.get("content", "")
        norm = _normalize(content)
        if norm in existing_normalized or norm in seen:
            continue
        seen.add(norm)
        result.append(p)
    return result


def _find_intent(config: BotConfig, intent_id: str):
    """Find an intent in the config or raise 404."""
    for intent in config.intents:
        if intent.id == intent_id:
            return intent
    raise HTTPException(404, f"Intent '{intent_id}' not found")


def _other_intents(config: BotConfig, intent_id: str) -> list[dict[str, str]]:
    """Return label+definition of all intents except the target."""
    return [
        {"label": i.label, "definition": i.definition}
        for i in config.intents
        if i.id != intent_id and i.label
    ]


async def handle_assistant_request(
    bot_id: str,
    config: BotConfig,
    req: AssistantRequest,
) -> AssistantResponse:
    """Process an assistant request and return proposals."""
    if req.use_case != UseCase.A2_EXAMPLES:
        raise HTTPException(400, f"Unsupported use case: {req.use_case}")

    intent = _find_intent(config, req.intent_id)
    others = _other_intents(config, req.intent_id)

    if req.sub_mode == SubMode.GENERATE:
        return await _handle_generate(bot_id, config, intent, others)
    elif req.sub_mode == SubMode.DISCRIMINATE:
        return await _handle_discriminate(bot_id, config, intent, others, req.context)
    elif req.sub_mode == SubMode.REVIEW:
        return await _handle_review(bot_id, config, intent, others)
    else:
        raise HTTPException(400, f"Unsupported sub-mode: {req.sub_mode}")


async def _handle_generate(bot_id, config, intent, others):
    """Generate new training examples."""
    messages = build_a2_generate_prompt(
        label=intent.label,
        definition=intent.definition,
        existing_examples=intent.examples,
        other_intents=others,
    )
    text, usage = await call_assistant_llm(bot_id, config, messages)
    items = _parse_json_array(text)
    items = _deduplicate(items, intent.examples)

    proposals = [
        Proposal(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id=intent.id,
            content=item.get("content", ""),
            rationale=item.get("rationale", ""),
        )
        for item in items
        if item.get("content", "").strip()
    ]
    return AssistantResponse(proposals=proposals, usage=usage)


async def _handle_discriminate(bot_id, config, intent, others, context):
    """Evaluate candidate examples."""
    candidates = context.get("candidates", [])
    if not candidates:
        return AssistantResponse(proposals=[], usage={})

    messages = build_a2_discriminate_prompt(
        label=intent.label,
        definition=intent.definition,
        candidates=candidates,
        other_intents=others,
    )
    text, usage = await call_assistant_llm(bot_id, config, messages)
    items = _parse_json_array(text)

    proposals = [
        Proposal(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.DISCRIMINATE,
            intent_id=intent.id,
            content=item.get("content", ""),
            rationale=item.get("rationale", ""),
            status="pending" if item.get("verdict") == "keep" else "rejected",
        )
        for item in items
        if item.get("content", "").strip()
    ]
    return AssistantResponse(proposals=proposals, usage=usage)


async def _handle_review(bot_id, config, intent, others):
    """Review existing examples for quality issues."""
    if not intent.examples:
        return AssistantResponse(proposals=[], usage={})

    messages = build_a2_review_prompt(
        label=intent.label,
        definition=intent.definition,
        examples=intent.examples,
        other_intents=others,
    )
    text, usage = await call_assistant_llm(bot_id, config, messages)
    items = _parse_json_array(text)

    proposals = [
        Proposal(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.REVIEW,
            intent_id=intent.id,
            content=item.get("content", ""),
            rationale=item.get("issue", "") + (
                f" → {item['suggestion']}" if item.get("suggestion") else ""
            ),
        )
        for item in items
        if item.get("content", "").strip()
    ]
    return AssistantResponse(proposals=proposals, usage=usage)
