"""
CSP (Content Security Policy) middleware (K5)
Implements PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Strict CSP for admin app, permissive for widget.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import secrets


class CSPMiddleware(BaseHTTPMiddleware):
    """
    Add Content-Security-Policy headers to responses.

    Admin app: Strict CSP with nonces
    Widget: Permissive (widget integrates into client pages)
    """

    async def dispatch(self, request: Request, call_next):
        # Generate nonce for this request
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        # Get response
        response: Response = await call_next(request)

        # Determine CSP based on path
        path = request.url.path

        if path.startswith("/widget"):
            # Widget: Permissive (client controls CSP)
            # Just document required directives in integration guide
            pass
        else:
            # Admin app: Strict CSP
            csp = self._get_strict_csp(nonce)
            response.headers["Content-Security-Policy"] = csp

            # Additional security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response

    def _get_strict_csp(self, nonce: str) -> str:
        """
        Generate strict CSP for admin app.

        Uses nonces for inline scripts (Vite generates some).
        """
        directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",  # Vite scripts
            f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline'",  # Tailwind needs unsafe-inline
            "img-src 'self' data: https:",  # data: for inline images, https: for external
            "font-src 'self' data:",
            "connect-src 'self'",  # API calls
            "frame-ancestors 'none'",  # Prevent clickjacking
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",  # No Flash, Java applets
            "upgrade-insecure-requests",  # Force HTTPS
        ]

        return "; ".join(directives)


def get_csp_nonce(request: Request) -> str:
    """
    Get CSP nonce for current request.

    Usage in templates:
        <script nonce="{{ csp_nonce }}">...</script>
    """
    return getattr(request.state, "csp_nonce", "")
