"""Q1 — Trial quota enforcement.

Default trial quotas:
- max_bots: 1
- max_intents_per_bot: 5
- max_examples_per_intent: 50
- max_documents: 20

Quotas are stored as JSON in accounts.quotas. If empty, defaults apply.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException

from loko.db.accounts import get_account

logger = logging.getLogger(__name__)

DEFAULT_QUOTAS = {
    "max_bots": 1,
    "max_intents_per_bot": 5,
    "max_examples_per_intent": 50,
    "max_documents": 20,
}

# Plans with unlimited quotas
_UNLIMITED_PLANS = frozenset({"standard", "enterprise", "internal"})


def get_effective_quotas(account_id: str) -> dict[str, int]:
    """Return effective quotas for an account (defaults + overrides)."""
    account = get_account(account_id)
    if not account:
        return DEFAULT_QUOTAS.copy()

    plan = account.get("plan", "trial")
    if plan in _UNLIMITED_PLANS:
        return {k: 999_999 for k in DEFAULT_QUOTAS}

    quotas = DEFAULT_QUOTAS.copy()
    stored = account.get("quotas", "")
    if stored:
        try:
            overrides = json.loads(stored) if isinstance(stored, str) else stored
            quotas.update({k: v for k, v in overrides.items() if k in DEFAULT_QUOTAS})
        except (json.JSONDecodeError, AttributeError):
            pass
    return quotas


def check_bot_creation_quota(account_id: str) -> None:
    """Q1: Raise 403 if account has reached max_bots."""
    if not account_id:
        return  # Ops/internal — no quota

    from loko.bot.config_store import list_bots
    quotas = get_effective_quotas(account_id)
    current_bots = list_bots(account_id=account_id)

    if len(current_bots) >= quotas["max_bots"]:
        raise HTTPException(
            403,
            f"Quota atteint : {quotas['max_bots']} bot(s) maximum pour votre forfait. "
            f"Passez au forfait Standard pour creer plus de bots.",
        )


def check_intent_quota(account_id: str, intent_count: int) -> None:
    """Q1: Raise 403 if intent count exceeds quota."""
    if not account_id:
        return

    quotas = get_effective_quotas(account_id)
    if intent_count > quotas["max_intents_per_bot"]:
        raise HTTPException(
            403,
            f"Quota atteint : {quotas['max_intents_per_bot']} intentions maximum pour votre forfait.",
        )


def check_document_quota(account_id: str, bot_id: str) -> None:
    """Q1: Raise 403 if document count exceeds quota."""
    if not account_id:
        return

    quotas = get_effective_quotas(account_id)
    try:
        from loko.bot.knowledge_store import get_knowledge_store
        store = get_knowledge_store(bot_id)
        docs = store.list_documents()
        if len(docs) >= quotas["max_documents"]:
            raise HTTPException(
                403,
                f"Quota atteint : {quotas['max_documents']} documents maximum pour votre forfait.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Knowledge store may not exist yet
