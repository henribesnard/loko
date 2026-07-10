"""Tests for R1 — rate limiting on public API endpoints."""

from __future__ import annotations

import os

import pytest


def test_composite_key_uses_api_key_hash():
    """Two different API keys get different rate-limit identities."""
    from loko.api.rate_limit import _composite_key_func

    class FakeRequest:
        def __init__(self, api_key=None, ip="1.2.3.4"):
            self.headers = {}
            if api_key:
                self.headers["X-API-Key"] = api_key
            self.client = type("C", (), {"host": ip})()

    r1 = FakeRequest(api_key="key-aaa")
    r2 = FakeRequest(api_key="key-bbb")
    r3 = FakeRequest()  # no key, IP-based

    assert _composite_key_func(r1) != _composite_key_func(r2)
    assert _composite_key_func(r1).startswith("key:")
    assert _composite_key_func(r3).startswith("ip:")


def test_composite_key_same_key_same_identity():
    """Same API key always produces the same identity."""
    from loko.api.rate_limit import _composite_key_func

    class FakeRequest:
        def __init__(self):
            self.headers = {"X-API-Key": "my-stable-key"}
            self.client = type("C", (), {"host": "10.0.0.1"})()

    assert _composite_key_func(FakeRequest()) == _composite_key_func(FakeRequest())


def test_require_limiter_in_server_mode_raises(monkeypatch):
    """In server mode without slowapi, startup must fail."""
    monkeypatch.setenv("LOKO_MODE", "server")
    # Simulate slowapi not importable
    import sys
    saved = sys.modules.get("slowapi")
    sys.modules["slowapi"] = None  # type: ignore[assignment]
    try:
        from loko.api.rate_limit import require_limiter_in_server_mode
        with pytest.raises(RuntimeError, match="slowapi"):
            require_limiter_in_server_mode()
    finally:
        if saved is not None:
            sys.modules["slowapi"] = saved
        else:
            sys.modules.pop("slowapi", None)


def test_require_limiter_desktop_mode_ok(monkeypatch):
    """In desktop mode, missing slowapi is not fatal."""
    monkeypatch.setenv("LOKO_MODE", "desktop")
    from loko.api.rate_limit import require_limiter_in_server_mode
    # Should not raise
    require_limiter_in_server_mode()


def test_rate_limit_defaults():
    """Env-based rate limit defaults are correct."""
    from loko.api import rate_limit
    # defaults when env vars are not set
    assert "minute" in rate_limit.RATE_SESSIONS
    assert "minute" in rate_limit.RATE_MESSAGES
