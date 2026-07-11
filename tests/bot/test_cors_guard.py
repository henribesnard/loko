"""H2 — CORS credentials guard: wildcard or empty origins with credentials must fail."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest


def _fresh_create_app():
    """Import create_app fresh (bypass module cache)."""
    # Remove cached module so create_app runs with current env
    mods_to_remove = [k for k in sys.modules if k.startswith("loko.main")]
    for m in mods_to_remove:
        del sys.modules[m]
    from loko.main import create_app

    return create_app


def test_cors_wildcard_server_mode_refused():
    """Boot in server mode with LOKO_CORS_ORIGINS='*' must raise RuntimeError."""
    env = {
        "LOKO_MODE": "server",
        "LOKO_CORS_ORIGINS": "*",
        "LOKO_ADMIN_TOKEN": "test-token",
    }
    with mock.patch.dict(os.environ, env, clear=False):
        with pytest.raises(RuntimeError, match="CORS misconfiguration"):
            _fresh_create_app()


def test_cors_explicit_origins_desktop_mode_ok():
    """Boot in desktop mode with default origins must succeed (no CORS guard)."""
    env = {"LOKO_MODE": "desktop"}
    with mock.patch.dict(os.environ, env, clear=False):
        # Remove LOKO_CORS_ORIGINS to use defaults
        os.environ.pop("LOKO_CORS_ORIGINS", None)
        create_app = _fresh_create_app()
        app = create_app()
        assert app is not None
