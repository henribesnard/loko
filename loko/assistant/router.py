"""LOKO Assistant — API router.

Prefix: /api/bot (mounted alongside bot_admin router)
Endpoints:
  POST /{bot_id}/assistant/ask    — Generate proposals
  POST /{bot_id}/assistant/accept — Accept proposals (add examples)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from loko.api.session_middleware import require_tenant_or_ops
from loko.bot.config_store import load_bot_config, save_bot_config
from loko.bot.llm.openai_compat import LLMProviderError
from loko.bot.models import ExampleMeta

from loko.assistant.proposals import AcceptRequest, AssistantRequest
from loko.assistant.quota import check_assistant_quota, increment_assistant_usage
from loko.assistant.service import handle_assistant_request

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bot",
    tags=["assistant"],
)


def _reject_demo_mutation(config, bot_id: str) -> None:
    if config and config.demo:
        raise HTTPException(403, f"Bot '{bot_id}' is a demo bot (read-only).")


@router.post("/{bot_id}/assistant/ask")
async def assistant_ask(
    bot_id: str,
    req: AssistantRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Generate assistant proposals for a given use case."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    # Quota check
    is_ops = getattr(request.state, "is_ops", False)
    account_id = "" if is_ops else request.state.account_id
    check_assistant_quota(account_id)

    try:
        result = await handle_assistant_request(bot_id, config, req)
    except LLMProviderError as exc:
        logger.error("Assistant LLM error for bot %s: %s", bot_id, exc)
        raise HTTPException(503, "assistant_llm_unavailable")

    # Increment quota after successful call
    increment_assistant_usage(account_id)

    # Audit
    try:
        from loko.db.audit import AuditLogger

        auditor = AuditLogger()
        auditor.log(
            action=AuditLogger.ACTION_ASSISTANT_ASK,
            user_id=getattr(request.state, "user_id", None),
            resource_id=bot_id,
            ip_address=request.client.host if request.client else None,
            details={
                "use_case": req.use_case.value,
                "sub_mode": req.sub_mode.value,
                "intent_id": req.intent_id,
                "proposals_count": len(result.proposals),
            },
        )
    except Exception:
        logger.debug("Audit logging failed for assistant.ask", exc_info=True)

    return result.model_dump(mode="json")


@router.post("/{bot_id}/assistant/accept")
async def assistant_accept(
    bot_id: str,
    req: AcceptRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Accept proposals: add examples to the target intent(s)."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    if not req.items:
        return {"added": 0, "intents": [i.model_dump(mode="json") for i in config.intents]}

    # Build lookup
    intents_by_id = {i.id: i for i in config.intents}
    added = 0

    for item in req.items:
        intent = intents_by_id.get(item.intent_id)
        if not intent:
            raise HTTPException(404, f"Intent '{item.intent_id}' not found")

        content = item.content.strip()
        if not content:
            continue

        # Avoid exact duplicates
        if content in intent.examples:
            continue

        intent.examples.append(content)
        intent.examples_metadata.append(
            ExampleMeta(index=len(intent.examples) - 1, origin="assistant")
        )
        added += 1

    if added > 0:
        save_bot_config(config)

    # Audit
    try:
        from loko.db.audit import AuditLogger

        auditor = AuditLogger()
        auditor.log(
            action=AuditLogger.ACTION_ASSISTANT_ACCEPT,
            user_id=getattr(request.state, "user_id", None),
            resource_id=bot_id,
            ip_address=request.client.host if request.client else None,
            details={"added": added},
        )
    except Exception:
        logger.debug("Audit logging failed for assistant.accept", exc_info=True)

    return {
        "added": added,
        "intents": [i.model_dump(mode="json") for i in config.intents],
    }
