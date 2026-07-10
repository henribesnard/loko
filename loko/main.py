"""LOKO — Main FastAPI application.

Assembles all routers and middleware.
Run with: uvicorn loko.main:app --reload
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from loko.api.bot_admin import router as bot_admin_router
from loko.api.bot_dashboard import router as bot_dashboard_router
from loko.api.bot_public import router as bot_public_router
from loko.api.user_auth import router as user_auth_router
from loko.api.ops import router as ops_router

logger = logging.getLogger(__name__)

# Static file directories
WIDGET_DIR = Path(__file__).parent.parent / "widget"
FRONTEND_DIR = Path(__file__).parent.parent / "desktop" / "dist"

# Default CORS origins (localhost for desktop)
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:1420",
    "http://localhost:5173",
    "http://127.0.0.1:1420",
    "http://127.0.0.1:5173",
    "tauri://localhost",
]


# ---------------------------------------------------------------------------
# Security headers middleware (P0-3)
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # X-Frame-Options: DENY except for widget (which is meant to be embedded)
        if not request.url.path.startswith("/widget"):
            response.headers["X-Frame-Options"] = "DENY"

        # Minimal CSP for HTML responses
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data:; "
                "connect-src 'self'"
            )

        return response


# ---------------------------------------------------------------------------
# Rate limiting (P0-5)
# ---------------------------------------------------------------------------

def _setup_rate_limiting(app: FastAPI) -> None:
    """Configure slowapi rate limiting.

    The Limiter instance is created in loko.api.rate_limit (shared module)
    to avoid circular imports.  Per-route limits are applied via @_apply_limit
    decorators directly on the endpoints in bot_public.py.
    """
    from loko.api.rate_limit import get_limiter, require_limiter_in_server_mode

    # Fail-closed: in server mode, refuse to start without slowapi
    require_limiter_in_server_mode()

    limiter = get_limiter()
    if limiter is None:
        logger.warning("slowapi not installed — rate limiting disabled")
        return

    app.state.limiter = limiter

    try:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Session purge background task (P1-7)
# ---------------------------------------------------------------------------

async def _session_purge_task() -> None:
    """Periodically purge expired sessions (RGPD compliance) and orphan locks (R4)."""
    retention_days = int(os.environ.get("LOKO_SESSION_RETENTION_DAYS", "30"))
    demo_retention_hours = 24  # Q5: demo bot sessions purged after 24h
    interval_minutes = 60  # Check every hour

    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)

            from loko.bot.config_store import list_bots, load_bot_config
            from loko.bot.session_store import get_session_store

            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).isoformat()

            # Q5: tighter cutoff for demo bots
            demo_cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=demo_retention_hours)
            ).isoformat()

            # Collect active session IDs across all bots (R4)
            active_session_ids: set[str] = set()

            bots = list_bots()
            for bot_info in bots:
                try:
                    bot_id = bot_info["bot_id"]
                    store = get_session_store(bot_id)

                    # Q5: use tighter cutoff for demo bots
                    config = load_bot_config(bot_id)
                    effective_cutoff = demo_cutoff if (config and config.demo) else cutoff

                    purged = store.purge_expired(bot_id, effective_cutoff)
                    if purged:
                        logger.info(
                            "Purged %d expired sessions for bot %s%s",
                            purged,
                            bot_id,
                            " (demo)" if (config and config.demo) else "",
                        )
                    # Gather surviving session IDs for lock cleanup
                    for s in store.list_sessions(bot_id, limit=100_000):
                        active_session_ids.add(s["session_id"])
                except Exception:
                    logger.exception(
                        "Error purging sessions for bot %s", bot_info["bot_id"]
                    )

            # R4: purge orphan locks
            from loko.api.bot_public import purge_session_locks

            locks_removed = purge_session_locks(active_session_ids)
            if locks_removed:
                logger.info("Purged %d orphan session locks", locks_removed)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Session purge task error")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="LOKO Bot Service",
        version="0.3.6",
        description="Deterministic chatbot platform for customer service.",
    )

    # --- CORS (P0-3 + H2: credentials guard) ---
    cors_env = os.environ.get("RAGKIT_CORS_ORIGINS", "")
    if cors_env:
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        origins = _DEFAULT_CORS_ORIGINS

    # H2: fail-closed — refuse to boot if credentials + wildcard origin
    mode = os.environ.get("RAGKIT_MODE", "desktop")
    if mode == "server" and ("*" in origins or not origins):
        raise RuntimeError(
            "CORS misconfiguration: allow_credentials=True requires an explicit "
            "origin list (RAGKIT_CORS_ORIGINS). Wildcard '*' or empty origins "
            "are not allowed in server mode with credentials."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Admin-Token", "X-CSRF-Token"],
    )

    # --- S6: CSRF double-submit cookie ---
    from loko.api.csrf import CSRFMiddleware
    app.add_middleware(CSRFMiddleware)

    # --- Security headers (P0-3) ---
    app.add_middleware(SecurityHeadersMiddleware)

    # --- Rate limiting (P0-5) ---
    _setup_rate_limiting(app)

    # --- K1: ModelIntegrityError → 422 with machine code ---
    from loko.bot.errors import ModelIntegrityError

    @app.exception_handler(ModelIntegrityError)
    async def _model_integrity_handler(request: Request, exc: ModelIntegrityError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "model_integrity",
                "code": exc.code,
                "detail": exc.detail,
                "bot_id": exc.bot_id,
            },
        )

    # --- Routers ---
    admin_token = os.environ.get("LOKO_ADMIN_TOKEN")

    # T2: admin/dashboard routes are always mounted — auth is per-route
    # (require_tenant_or_ops does session-based tenant check or ops token)
    app.include_router(bot_admin_router)
    app.include_router(bot_dashboard_router)

    app.include_router(bot_public_router)

    # --- User auth (always mounted) ---
    app.include_router(user_auth_router)

    # --- Ops (super-admin, guarded by LOKO_ADMIN_TOKEN) ---
    if mode == "server" and admin_token:
        app.include_router(ops_router)
    elif mode != "server":
        # Desktop mode: mount ops without mandatory token
        app.include_router(ops_router)

    # --- API key management routes ---
    _mount_api_key_routes(app, mode, admin_token)

    # --- Widget static files ---
    if WIDGET_DIR.exists():
        app.mount(
            "/widget",
            StaticFiles(directory=str(WIDGET_DIR)),
            name="widget",
        )

    # --- Health ---
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "loko-bot"}

    # --- L4: recover interrupted training jobs on boot ---
    @app.on_event("startup")
    async def recover_training_jobs():
        from loko.api.bot_admin import recover_interrupted_jobs
        recover_interrupted_jobs()

    # --- W1.2: check published bots for model availability at boot ---
    @app.on_event("startup")
    async def check_published_bots():
        """Scan all published bots and log CRITICAL for unavailable models.

        V1-4 requirement: exploitant must see incident at boot, not just at first request.
        Behavior: server starts anyway (fail-fast per request), but logs warn operator.
        """
        import logging
        from loko.bot.config_store import list_bots, load_bot_config
        from loko.bot.classifier.loader import load_classifier
        from loko.bot.errors import ComponentUnavailableError

        logger = logging.getLogger("loko.boot")

        try:
            all_bots = list_bots()
            published_bots = []

            for bot_info in all_bots:
                bot_id = bot_info.get("bot_id")
                if not bot_id:
                    continue

                try:
                    config = load_bot_config(bot_id)
                    if config and config.status == "published":
                        published_bots.append((bot_id, config.name))
                except Exception:
                    pass  # Skip bots with config errors (will be caught in runtime)

            if not published_bots:
                logger.info("No published bots found at startup")
                return

            logger.info(f"Checking {len(published_bots)} published bot(s) for model availability...")

            unavailable_count = 0
            for bot_id, bot_name in published_bots:
                try:
                    # Try to load the classifier (will raise ComponentUnavailableError if missing)
                    _ = load_classifier(bot_id)
                    logger.debug(f"Bot {bot_id} ({bot_name}): classifier available")
                except ComponentUnavailableError as exc:
                    # CRITICAL: model unavailable for published bot
                    # Log bot_id and error code, NO disk paths (security)
                    error_code = getattr(exc, "code", "unknown")
                    logger.critical(
                        f"Published bot unavailable at startup: "
                        f"bot_id={bot_id} name='{bot_name}' "
                        f"error=classifier_l1_unavailable code={error_code}"
                    )
                    unavailable_count += 1
                except Exception as exc:
                    # Unexpected error during check (not a known ComponentUnavailableError)
                    logger.error(
                        f"Unexpected error checking bot {bot_id} ({bot_name}): "
                        f"{type(exc).__name__}: {exc}"
                    )

            if unavailable_count > 0:
                logger.critical(
                    f"STARTUP CHECK: {unavailable_count}/{len(published_bots)} published bot(s) "
                    f"have unavailable models - they will fail-fast on requests"
                )
            else:
                logger.info(f"All {len(published_bots)} published bot(s) have available models")

        except Exception as exc:
            # Don't crash server if startup check itself fails
            logger.error(f"Failed to check published bots at startup: {exc}")

    # --- Session purge background task (P1-7) ---
    @app.on_event("startup")
    async def start_purge_task():
        asyncio.create_task(_session_purge_task())

    # --- SPA fallback (C4) ---
    if FRONTEND_DIR.exists():
        index_html = FRONTEND_DIR / "index.html"

        # Mount static assets first
        app.mount(
            "/assets",
            StaticFiles(directory=str(FRONTEND_DIR / "assets")),
            name="frontend-assets",
        ) if (FRONTEND_DIR / "assets").exists() else None

        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> Response:
            """Serve SPA — return index.html for non-API/non-static routes."""
            # Don't intercept API requests — let them 404 normally
            if path.startswith("api/") or path.startswith("health"):
                return JSONResponse({"detail": "Not found"}, status_code=404)

            # Try to serve static file first
            static_path = FRONTEND_DIR / path
            if static_path.is_file() and static_path.resolve().is_relative_to(
                FRONTEND_DIR.resolve()
            ):
                return FileResponse(static_path)
            # Fallback to SPA index
            if index_html.exists():
                return FileResponse(index_html)
            return JSONResponse({"detail": "Not found"}, status_code=404)

    return app


def _mount_api_key_routes(app: FastAPI, mode: str, admin_token: str | None) -> None:
    """Mount API key management routes — T2: guarded by require_tenant_or_ops."""
    from fastapi import APIRouter, Depends, HTTPException
    from pydantic import BaseModel, Field

    from loko.api.api_keys import (
        generate_api_key,
        list_api_keys,
        revoke_api_key,
    )
    from loko.api.session_middleware import require_tenant_or_ops

    keys_router = APIRouter(
        prefix="/api/bot",
        tags=["bot-api-keys"],
    )

    class CreateKeyRequest(BaseModel):
        label: str = ""
        allowed_origins: list[str] = Field(default_factory=list)

    @keys_router.post("/{bot_id}/api-keys", status_code=201)
    async def create_api_key(
        bot_id: str, req: CreateKeyRequest, request: Request = None,
        _auth=Depends(require_tenant_or_ops),
    ) -> dict:
        raw_key, key_id = generate_api_key(
            bot_id, label=req.label, allowed_origins=req.allowed_origins,
        )
        return {"raw_key": raw_key, "key_id": key_id}

    @keys_router.get("/{bot_id}/api-keys")
    async def list_keys(
        bot_id: str, request: Request = None, _auth=Depends(require_tenant_or_ops),
    ) -> list[dict]:
        return list_api_keys(bot_id)

    @keys_router.delete("/{bot_id}/api-keys/{key_id}")
    async def revoke_key(
        bot_id: str, key_id: str, request: Request = None,
        _auth=Depends(require_tenant_or_ops),
    ) -> dict:
        if not revoke_api_key(bot_id, key_id):
            raise HTTPException(404, "Key not found")
        return {"status": "revoked", "key_id": key_id}

    app.include_router(keys_router)


app = create_app()
