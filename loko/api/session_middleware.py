"""LOKO — Session middleware for authenticated routes.

FastAPI dependency that validates the session cookie and injects
current_user and current_account_id into the request state.
"""

from __future__ import annotations

import logging
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

    # Store in request state for downstream access
    request.state.user_id = session["user_id"]
    request.state.account_id = session["account_id"]
    request.state.user_email = session["email"]
    request.state.user_role = session["role"]

    return session
