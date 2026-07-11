"""LOKO Bot — Authentication & authorization dependencies.

Provides FastAPI dependencies for:
  - Bot API key authentication (public endpoints)
  - Admin token authentication (admin/dashboard endpoints)
  - bot_id path parameter validation
"""

from __future__ import annotations

import hmac
import logging
import os
import re

from fastapi import HTTPException, Request

from loko.api.api_keys import (
    APIKeyRecord,
    check_origin,
    validate_api_key_for_bot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# bot_id validation (P0-4)
# ---------------------------------------------------------------------------

BOT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
# Also allow UUID format for existing bots
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_bot_id(bot_id: str) -> str:
    """Validate bot_id path parameter — reject traversal attempts."""
    if not (BOT_ID_RE.match(bot_id) or UUID_RE.match(bot_id)):
        raise HTTPException(
            status_code=422,
            detail="Invalid bot_id format",
        )
    return bot_id


# ---------------------------------------------------------------------------
# API key authentication for public endpoints (P0-1)
# ---------------------------------------------------------------------------


async def require_bot_api_key(
    bot_id: str,
    request: Request,
) -> APIKeyRecord:
    """FastAPI dependency: validate API key for a specific bot.

    Reads the key from Authorization: Bearer <key> or X-API-Key header.
    Validates the key against the bot's stored keys and checks origin.

    Returns the validated APIKeyRecord.
    """
    client_ip = request.client.host if request.client else "unknown"
    raw_key = _extract_api_key(request)

    if not raw_key:
        logger.warning("Auth failure: no API key — IP=%s bot=%s", client_ip, bot_id)
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    record = validate_api_key_for_bot(raw_key, bot_id)
    if not record:
        # Intentionally vague: don't reveal if bot exists vs key invalid
        logger.warning(
            "Auth failure: invalid API key — IP=%s bot=%s", client_ip, bot_id
        )
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    # Origin check
    origin = request.headers.get("origin")
    if not check_origin(record, origin):
        logger.warning(
            "Auth failure: origin rejected — IP=%s bot=%s key=%s origin=%s",
            client_ip,
            bot_id,
            record.key_id,
            origin,
        )
        raise HTTPException(
            status_code=403,
            detail="Origin not allowed",
        )

    return record


def _extract_api_key(request: Request) -> str | None:
    """Extract API key from request headers."""
    # Try Authorization: Bearer <key>
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # Fallback: X-API-Key header
    return request.headers.get("x-api-key")


# ---------------------------------------------------------------------------
# Admin token authentication (P0-2)
# ---------------------------------------------------------------------------


def _get_admin_token() -> str | None:
    """Read the admin token from environment."""
    return os.environ.get("LOKO_ADMIN_TOKEN")


def _get_mode() -> str:
    """Read LOKO_MODE from environment (default: desktop)."""
    from loko.config.env import get_env

    return get_env("MODE", "desktop")


async def require_admin(request: Request) -> None:
    """FastAPI dependency: require admin token.

    In server mode: LOKO_ADMIN_TOKEN must be set and matched.
    In desktop mode: token is optional (Tauri passes ephemeral token).
    """
    admin_token = _get_admin_token()
    mode = _get_mode()

    # In server mode, admin token is mandatory
    if mode == "server" and not admin_token:
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured (LOKO_ADMIN_TOKEN missing)",
        )

    # If a token is configured, enforce it
    if admin_token:
        client_ip = request.client.host if request.client else "unknown"
        provided = _extract_admin_token(request)
        if not provided:
            logger.warning("Admin auth failure: no token — IP=%s", client_ip)
            raise HTTPException(status_code=401, detail="Authentication required")
        if not hmac.compare_digest(provided, admin_token):
            logger.warning("Admin auth failure: invalid token — IP=%s", client_ip)
            raise HTTPException(status_code=401, detail="Authentication required")


def _extract_admin_token(request: Request) -> str | None:
    """Extract admin token from request headers."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.headers.get("x-admin-token")
