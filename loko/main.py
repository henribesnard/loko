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
from loko import __version__
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
# API Documentation Protection (C3)
# ---------------------------------------------------------------------------


class APIDocsMiddleware(BaseHTTPMiddleware):
    """Protect API documentation endpoints with admin token (server mode only)."""

    async def dispatch(self, request: Request, call_next):
        from loko.config.env import get_env
        import hmac

        # Only protect docs in server mode
        mode = get_env("MODE", "desktop")
        docs_paths = ["/api/docs", "/api/redoc", "/api/openapi.json"]

        if mode == "server" and any(request.url.path == path for path in docs_paths):
            admin_token = os.environ.get("LOKO_ADMIN_TOKEN")

            if not admin_token:
                # Admin token not configured - deny access
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "API documentation not configured (LOKO_ADMIN_TOKEN missing)"
                    },
                )

            # Extract token from Authorization header or query param
            auth_header = request.headers.get("Authorization", "")
            token_from_header = None
            if auth_header.startswith("Bearer "):
                token_from_header = auth_header[7:]

            # Allow token in query param for browser access (e.g., /api/docs?token=...)
            token_from_query = request.query_params.get("token")

            provided_token = token_from_header or token_from_query

            if not provided_token or not hmac.compare_digest(
                provided_token, admin_token
            ):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required for API documentation"},
                )

        return await call_next(request)


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
                    effective_cutoff = (
                        demo_cutoff if (config and config.demo) else cutoff
                    )

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


async def _alert_evaluation_task() -> None:
    """PRO-5: Periodically evaluate alert rules against bot metrics."""
    interval_minutes = int(os.environ.get("LOKO_ALERT_INTERVAL_MIN", "5"))

    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)

            from loko.bot.config_store import list_bots
            from loko.bot.session_store import get_bot_dir

            bots = list_bots()
            for bot_info in bots:
                bot_id = bot_info["bot_id"]
                try:
                    # Load alert rules for this bot
                    alert_config_path = get_bot_dir(bot_id) / "alerts.json"
                    if not alert_config_path.is_file():
                        continue

                    import json as _json

                    alert_data = _json.loads(
                        alert_config_path.read_text(encoding="utf-8")
                    )
                    rules_data = alert_data.get("rules", [])
                    if not rules_data:
                        continue

                    from loko.bot.alerting import AlertEngine, AlertRule

                    rules = [AlertRule(**r) for r in rules_data]
                    engine = AlertEngine(rules)

                    # Gather current metrics (best-effort from available data)
                    metrics: dict[str, float] = {}
                    try:
                        from loko.bot.session_store import get_session_store

                        store = get_session_store(bot_id)
                        stats = (
                            store.get_session_stats(bot_id)
                            if hasattr(store, "get_session_stats")
                            else {}
                        )
                        metrics.update(stats)
                    except Exception:
                        logger.debug("Could not gather session stats for bot %s", bot_id)

                    events = engine.evaluate(metrics)
                    for event in events:
                        if event.resolved:
                            logger.info(
                                "Alert resolved: bot=%s rule=%s metric=%s value=%.2f",
                                bot_id,
                                event.rule_id,
                                event.metric,
                                event.value,
                            )
                        else:
                            logger.warning(
                                "Alert triggered: bot=%s rule=%s metric=%s "
                                "value=%.2f threshold=%.2f",
                                bot_id,
                                event.rule_id,
                                event.metric,
                                event.value,
                                event.threshold,
                            )

                except Exception:
                    logger.debug("Alert evaluation skipped for bot %s", bot_id)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Alert evaluation task error")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # C3: Expose API documentation at /api/docs (protected by admin token)
    app = FastAPI(
        title="LOKO API",
        version=__version__,
        description="Deterministic chatbot platform for customer service.",
        docs_url="/api/docs",  # Swagger UI
        redoc_url="/api/redoc",  # ReDoc
        openapi_url="/api/openapi.json",
    )

    # --- CORS (P0-3 + H2: credentials guard) ---
    from loko.config.env import get_env

    cors_env = get_env("CORS_ORIGINS", "")
    if cors_env:
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        origins = _DEFAULT_CORS_ORIGINS

    # H2: fail-closed — refuse to boot if credentials + wildcard origin
    mode = get_env("MODE", "desktop")
    if mode == "server" and ("*" in origins or not origins):
        raise RuntimeError(
            "CORS misconfiguration: allow_credentials=True requires an explicit "
            "origin list (LOKO_CORS_ORIGINS). Wildcard '*' or empty origins "
            "are not allowed in server mode with credentials."
        )

    # B3: fail-closed — verify LOKO_SECRET_KEY at boot in server mode
    if mode == "server":
        from loko.security.secret_store import verify_master_key

        verify_master_key()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Admin-Token",
            "X-CSRF-Token",
        ],
    )

    # --- S6: CSRF double-submit cookie ---
    from loko.api.csrf import CSRFMiddleware

    app.add_middleware(CSRFMiddleware)

    # --- Security headers (P0-3) ---
    app.add_middleware(SecurityHeadersMiddleware)

    # --- C3: API documentation protection ---
    app.add_middleware(APIDocsMiddleware)

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

    # --- Assistant (feature-flagged) ---
    if os.environ.get("LOKO_ASSISTANT_ENABLED", "").lower() in ("1", "true", "yes"):
        from loko.assistant.router import router as assistant_router

        app.include_router(assistant_router)
        logger.info("Assistant router mounted (LOKO_ASSISTANT_ENABLED=true)")

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
        return {"status": "ok", "service": "loko-bot", "version": __version__}

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
        from loko.bot.config_store import list_bots, load_bot_config
        from loko.bot.classifier.loader import load_classifier
        from loko.bot.errors import ComponentUnavailableError

        boot_logger = logging.getLogger("loko.boot")

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
                    boot_logger.debug("Skipping bot %s with config errors", bot_info.get("bot_id"))

            if not published_bots:
                boot_logger.info("No published bots found at startup")
                return

            boot_logger.info(
                "Checking %d published bot(s) for model availability...",
                len(published_bots),
            )

            unavailable_count = 0
            for bot_id, bot_name in published_bots:
                try:
                    # Try to load the classifier (will raise ComponentUnavailableError if missing)
                    _ = load_classifier(bot_id)
                    boot_logger.debug("Bot %s (%s): classifier available", bot_id, bot_name)
                except ComponentUnavailableError as exc:
                    # CRITICAL: model unavailable for published bot
                    # Log bot_id and error code, NO disk paths (security)
                    error_code = getattr(exc, "code", "unknown")
                    boot_logger.critical(
                        "Published bot unavailable at startup: "
                        "bot_id=%s name='%s' error=classifier_l1_unavailable code=%s",
                        bot_id, bot_name, error_code,
                    )
                    unavailable_count += 1
                except Exception as exc:
                    # Unexpected error during check (not a known ComponentUnavailableError)
                    boot_logger.error(
                        "Unexpected error checking bot %s (%s): %s: %s",
                        bot_id, bot_name, type(exc).__name__, exc,
                    )

            if unavailable_count > 0:
                boot_logger.critical(
                    "STARTUP CHECK: %d/%d published bot(s) "
                    "have unavailable models - they will fail-fast on requests",
                    unavailable_count, len(published_bots),
                )
            else:
                boot_logger.info(
                    "All %d published bot(s) have available models",
                    len(published_bots),
                )

        except Exception as exc:
            # Don't crash server if startup check itself fails
            boot_logger.error("Failed to check published bots at startup: %s", exc)

    # --- Session purge background task (P1-7) ---
    @app.on_event("startup")
    async def start_purge_task():
        asyncio.create_task(_session_purge_task())

    # --- PRO-5: Alert evaluation background task ---
    @app.on_event("startup")
    async def start_alert_task():
        asyncio.create_task(_alert_evaluation_task())

    # --- SPA fallback (C4) ---
    if FRONTEND_DIR.exists():
        index_html = FRONTEND_DIR / "index.html"

        # Mount static assets first
        if (FRONTEND_DIR / "assets").exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(FRONTEND_DIR / "assets")),
                name="frontend-assets",
            )

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
            # Fallback to SPA index — no-cache so CDN/proxy always fetches
            # fresh HTML (asset filenames contain hashes for cache-busting)
            if index_html.exists():
                resp = FileResponse(index_html)
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return resp
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
        bot_id: str,
        req: CreateKeyRequest,
        request: Request = None,
        _auth=Depends(require_tenant_or_ops),
    ) -> dict:
        raw_key, key_id = generate_api_key(
            bot_id,
            label=req.label,
            allowed_origins=req.allowed_origins,
        )
        return {"raw_key": raw_key, "key_id": key_id}

    @keys_router.get("/{bot_id}/api-keys")
    async def list_keys(
        bot_id: str,
        request: Request = None,
        _auth=Depends(require_tenant_or_ops),
    ) -> list[dict]:
        return list_api_keys(bot_id)

    @keys_router.delete("/{bot_id}/api-keys/{key_id}")
    async def revoke_key(
        bot_id: str,
        key_id: str,
        request: Request = None,
        _auth=Depends(require_tenant_or_ops),
    ) -> dict:
        if not revoke_api_key(bot_id, key_id):
            raise HTTPException(404, "Key not found")
        return {"status": "revoked", "key_id": key_id}

    app.include_router(keys_router)


app = create_app()
