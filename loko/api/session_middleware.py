"""LOKO — Session middleware for authenticated routes.

FastAPI dependency that validates the session cookie and injects
current_user and current_account_id into the request state.

T2: adds require_tenant_or_ops — dual guard for tenant isolation.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from loko.db.accounts import validate_session

logger = logging.getLogger(__name__)

_COOKIE_NAME = "loko_session"


async def require_session(request: Request) -> dict[str, Any]:
    """FastAPI dependency: require a valid session cookie.

    Returns the session data (includes user_id, account_id, email, etc.).
    Raises 401 if no valid session.
    """
    session_id = request.cookies.get(_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    # S7: sliding expiration — extend session if last refresh > 1h ago
    _maybe_extend_session(session)

    # Store in request state for downstream access
    request.state.user_id = session["user_id"]
    request.state.account_id = session["account_id"]
    request.state.user_email = session["email"]
    request.state.user_role = session["role"]

    return session


def _maybe_extend_session(session: dict[str, Any]) -> None:
    """S7/AR-3: extend session expiry by 7 days if last extended >1h ago."""
    try:
        from loko.db.accounts import get_db

        expires = datetime.fromisoformat(session["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=7)
        # Only extend if we'd gain more than 1 hour
        if new_expires - expires > timedelta(hours=1):
            db = get_db()
            db.execute(
                "UPDATE sessions SET expires_at = ? WHERE id = ?",
                (new_expires.isoformat(), session["id"]),
            )
            db.commit()
    except Exception:
        pass  # Non-critical — session still valid


# ---------------------------------------------------------------------------
# T2: Dual auth — session tenant OR ops token
# ---------------------------------------------------------------------------


def _is_ops_token_valid(request: Request) -> bool:
    """Check if the request carries a valid ops admin token."""
    admin_token = os.environ.get("LOKO_ADMIN_TOKEN")
    if not admin_token:
        return False
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:].strip()
    else:
        provided = request.headers.get("x-admin-token", "")
    if not provided:
        return False
    return hmac.compare_digest(provided, admin_token)


async def require_tenant(request: Request, bot_id: str) -> dict[str, Any]:
    """Validate session and verify the user owns the bot.

    Returns 404 (not 403) to avoid revealing resource existence.
    """
    session = await require_session(request)
    from loko.bot.config_store import load_bot_config

    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    if config.account_id != session["account_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return session


async def require_tenant_or_ops(request: Request, bot_id: str) -> dict[str, Any] | None:
    """T2: Dual guard — session tenant owner OR ops admin token.

    For session users: validates session + tenant ownership.
    For ops: validates LOKO_ADMIN_TOKEN (transverse access).
    Returns session dict for session users, None for ops.
    Raises 404 for tenant mismatch (never 403).
    Raises 401 if neither auth method succeeds.
    """
    # Try ops token first (no session needed)
    if _is_ops_token_valid(request):
        # Ops has transverse access — store marker
        request.state.is_ops = True
        request.state.account_id = None
        return None

    # Try session
    session_id = request.cookies.get(_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    _maybe_extend_session(session)

    # Store in request state
    request.state.user_id = session["user_id"]
    request.state.account_id = session["account_id"]
    request.state.user_email = session["email"]
    request.state.user_role = session["role"]
    request.state.is_ops = False

    # Check tenant ownership
    from loko.bot.config_store import load_bot_config

    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    if config.account_id != session["account_id"]:
        # Don't reveal existence — 404, not 403
        raise HTTPException(status_code=404, detail="Not found")

    return session


async def require_session_or_ops(request: Request) -> dict[str, Any] | None:
    """Auth guard for routes without bot_id (e.g., bot creation, list).

    Session users: filtered by account_id downstream.
    Ops: transverse access.
    """
    if _is_ops_token_valid(request):
        request.state.is_ops = True
        request.state.account_id = None
        return None

    return await require_session(request)
