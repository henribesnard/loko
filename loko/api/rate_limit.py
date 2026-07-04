"""LOKO Bot — Shared rate limiting configuration.

Provides a module-level Limiter instance that can be imported by routers
at definition time (avoiding circular imports with main.py).

Key function: composite — hashes the API key if present, else uses IP.
This prevents an attacker without a key from consuming a legitimate
client's quota behind the same NAT.
"""

from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Rate limit defaults (overridable via environment variables)
RATE_SESSIONS = os.environ.get("LOKO_RATE_SESSIONS", "10/minute")
RATE_MESSAGES = os.environ.get("LOKO_RATE_MESSAGES", "30/minute")
RATE_FEEDBACK = os.environ.get("LOKO_RATE_FEEDBACK", "30/minute")
RATE_READ = os.environ.get("LOKO_RATE_READ", "60/minute")


def _composite_key_func(request) -> str:  # noqa: ANN001
    """Return a rate-limit identity: hash of API key if present, else client IP.

    If the request carries an Authorization or X-API-Key header, the key
    hash is used as identity so that different keys have independent quotas.
    Otherwise, fall back to the remote address.
    """
    # Check for API key in headers
    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]

    # Fall back to IP
    if hasattr(request, "client") and request.client:
        return "ip:" + request.client.host
    return "ip:unknown"


# ---------------------------------------------------------------------------
# Limiter singleton (lazy — None if slowapi not installed)
# ---------------------------------------------------------------------------

_limiter = None


def get_limiter():
    """Return the shared Limiter instance, creating it on first call.

    Returns None if slowapi is not installed (desktop / dev mode).
    """
    global _limiter  # noqa: PLW0603
    if _limiter is not None:
        return _limiter

    try:
        from slowapi import Limiter

        _limiter = Limiter(key_func=_composite_key_func)
        return _limiter
    except ImportError:
        return None


def require_limiter_in_server_mode() -> None:
    """In RAGKIT_MODE=server, refuse to start without slowapi (fail-closed).

    Call this during app startup. In desktop mode, missing slowapi is
    a warning only.
    """
    mode = os.environ.get("RAGKIT_MODE", "desktop")
    if mode != "server":
        return

    try:
        import slowapi  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "RAGKIT_MODE=server requires slowapi for rate limiting. "
            "Install it with: pip install slowapi"
        ) from None
