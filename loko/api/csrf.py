"""S6 — CSRF protection via double-submit cookie.

In server mode, mutating requests (POST/PUT/PATCH/DELETE) on /api/bot and
/api/auth must include X-CSRF-Token matching the csrf_token cookie.

GET /api/auth/csrf-token sets the cookie.
The frontend reads the cookie and sends it as a header.
"""

from __future__ import annotations

import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths exempt from CSRF (public API uses API key, auth login/signup use credentials)
_EXEMPT_PREFIXES = (
    "/api/v1/",         # Public bot API (uses API key, no cookie)
    "/api/auth/login",  # Login sets the CSRF cookie
    "/api/auth/signup", # Signup is unauthenticated
    "/api/ops/",        # Ops uses Bearer token, no cookie
    "/health",
    "/widget/",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """S6: Double-submit cookie CSRF protection."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only enforce in server mode
        from loko.config.env import get_env
        if get_env("MODE", "desktop") != "server":
            return await call_next(request)

        # Safe methods and exempt paths skip CSRF
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Check double-submit: cookie must match header
        cookie_token = request.cookies.get(_CSRF_COOKIE, "")
        header_token = request.headers.get(_CSRF_HEADER, "")

        if not cookie_token or not header_token or cookie_token != header_token:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

        return await call_next(request)


def set_csrf_cookie(response: Response) -> str:
    """Generate a CSRF token, set it as a cookie (not HttpOnly), and return it."""
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=_CSRF_COOKIE,
        value=token,
        httponly=False,  # JS must read this
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return token
