"""LOKO — Ops (super-admin) API.

Router prefix: /api/ops
Protected by LOKO_ADMIN_TOKEN (same as existing require_admin).
Provides: account listing, quota management, account suspension, health.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from loko.api.auth import require_admin
from loko.db.accounts import get_account, list_accounts, update_account

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ops",
    tags=["ops"],
    dependencies=[Depends(require_admin)],
)


class UpdateAccountRequest(BaseModel):
    plan: str | None = None
    quotas: dict[str, Any] | None = None
    status: str | None = None


@router.get("/accounts")
async def ops_list_accounts() -> list[dict[str, Any]]:
    """List all accounts."""
    accounts = list_accounts()
    return accounts


@router.get("/accounts/{account_id}")
async def ops_get_account(account_id: str) -> dict[str, Any]:
    """Get a specific account."""
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.patch("/accounts/{account_id}")
async def ops_update_account(
    account_id: str, req: UpdateAccountRequest
) -> dict[str, Any]:
    """Update account fields (plan, quotas, status)."""
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    updates: dict[str, Any] = {}
    if req.plan is not None:
        updates["plan"] = req.plan
    if req.quotas is not None:
        updates["quotas"] = json.dumps(req.quotas)
    if req.status is not None:
        if req.status not in ("active", "suspended"):
            raise HTTPException(400, "Status must be 'active' or 'suspended'")
        updates["status"] = req.status

    if updates:
        update_account(account_id, **updates)

    return get_account(account_id) or {}


@router.get("/health")
async def ops_health() -> dict[str, Any]:
    """Extended health check for ops."""
    from loko.bot.config_store import list_bots

    bots = list_bots()
    accounts = list_accounts()
    return {
        "status": "ok",
        "total_bots": len(bots),
        "total_accounts": len(accounts),
    }
