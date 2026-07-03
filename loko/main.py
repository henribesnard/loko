"""LOKO — Main FastAPI application.

Assembles all routers and middleware.
Run with: uvicorn loko.main:app --reload
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from loko.api.bot_admin import router as bot_admin_router
from loko.api.bot_dashboard import router as bot_dashboard_router
from loko.api.bot_public import router as bot_public_router

logger = logging.getLogger(__name__)

# Widget static files directory
WIDGET_DIR = Path(__file__).parent.parent / "widget"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="LOKO Bot Service",
        version="0.1.0",
        description="Deterministic chatbot platform for customer service.",
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tightened per-bot via API key origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    app.include_router(bot_admin_router)
    app.include_router(bot_dashboard_router)
    app.include_router(bot_public_router)

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

    return app


app = create_app()
