"""LOKO — Role-based authorization middleware (A.3).

Role hierarchy: owner > editor > viewer.
- owner:  full access (team management, billing, deletion, bot CRUD)
- editor: bot CRUD, training, publish, playground
- viewer: read-only access to bots, dashboards, analytics, monitoring

Provides two dependency factories:
- require_role(min_role)         — for routes with bot_id (tenant + role check)
- require_account_role(min_role) — for routes without bot_id (/api/account/*)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from loko.api.session_middleware import _is_ops_token_valid, require_session
from loko.db.accounts import get_membership

logger = logging.getLogger(__name__)

ROLE_HIERARCHY: dict[str, int] = {"owner": 3, "editor": 2, "viewer": 1}


def require_role(min_role: str):
    """Factory: returns a FastAPI dependency that checks tenant + minimum role.

    Use on routes that receive a ``bot_id`` path parameter.
    """
    min_level = ROLE_HIERARCHY[min_role]

    async def _check(request: Request, bot_id: str) -> dict[str, Any] | None:
        # Ops admin token bypasses role checks (transverse access)
        if _is_ops_token_valid(request):
            request.state.is_ops = True
            request.state.account_id = None
            return None

        session = await require_session(request)

        # Tenant isolation: verify bot belongs to user's account
        from loko.bot.config_store import load_bot_config

        config = load_bot_config(bot_id)
        if not config:
            raise HTTPException(status_code=404, detail="Not found")
        if config.account_id != session["account_id"]:
            raise HTTPException(status_code=404, detail="Not found")

        # Role check via memberships table
        membership = get_membership(session["account_id"], session["user_id"])
        if not membership:
            raise HTTPException(status_code=403, detail="No membership found")
        user_level = ROLE_HIERARCHY.get(membership["role"], 0)
        if user_level < min_level:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        request.state.user_role = membership["role"]
        request.state.user_email = session.get("email", "")
        request.state.is_ops = False
        return session

    return _check


def require_account_role(min_role: str):
    """Factory: returns a FastAPI dependency that checks minimum role on account.

    Use on routes without bot_id (e.g. /api/account/team).
    """
    min_level = ROLE_HIERARCHY[min_role]

    async def _check(request: Request) -> dict[str, Any]:
        session = await require_session(request)

        membership = get_membership(session["account_id"], session["user_id"])
        if not membership:
            raise HTTPException(status_code=403, detail="No membership found")
        user_level = ROLE_HIERARCHY.get(membership["role"], 0)
        if user_level < min_level:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        request.state.user_role = membership["role"]
        request.state.user_email = session.get("email", "")
        return session

    return _check
