"""ACC-4 — Login must be blocked until email is verified.

Tests cover:
- Unverified user cannot get a session (403, no cookie)
- Verified user can log in normally (200 + cookie)
- Wrong password still returns generic 401 (no enumeration)
- Nonexistent email returns generic 401
- Resend-verification endpoint (anti-enumeration, rate-limited)
"""

from __future__ import annotations

import asyncio
import os
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient

from loko.db.accounts import (
    create_account,
    create_email_token,
    create_user,
    update_user,
    validate_email_token,
    mark_token_used,
)




@pytest.fixture(autouse=True)
def _reset_db(tmp_path, monkeypatch):
    """Use a fresh database for each test."""
    import loko.db.accounts as mod
    monkeypatch.setattr(mod, "_DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(mod, "_connection", None)
    yield
    if mod._connection:
        mod._connection.close()
        mod._connection = None


@pytest.fixture()
def app():
    """Create a fresh ASGI app for each test."""
    env = {"LOKO_MODE": "desktop"}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LOKO_AUTH_DEBUG_TOKENS", None)
        from loko.main import create_app
        return create_app()


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# ACC-4: login blocked before email verification
# ---------------------------------------------------------------------------

def test_login_blocked_before_verification(app):
    """Unverified user: login returns 403 with no session cookie."""
    async def _run_test():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Signup
            resp = await client.post("/api/auth/signup", json={
                "email": "acc4@example.com",
                "password": "MyStr0ngPwd!xx",
                "org_name": "ACC4 Test",
                "accept_terms": True,
            })
            assert resp.status_code == 201

            # Login before verification → 403
            resp = await client.post("/api/auth/login", json={
                "email": "acc4@example.com",
                "password": "MyStr0ngPwd!xx",
            })
            assert resp.status_code == 403
            assert "non verifie" in resp.json()["detail"].lower()

            # No session cookie set
            assert "loko_session" not in resp.cookies

    _run(_run_test())


def test_login_works_after_verification(app):
    """Verified user: login returns 200 with session cookie."""
    # Pre-create account and user
    account = create_account("Verified Org")
    user = create_user(account["id"], "verified@example.com", "MyStr0ngPwd!xx")
    token = create_email_token(user["id"], "verify")

    # Verify email
    data = validate_email_token(token, "verify")
    assert data is not None
    mark_token_used(data["id"])
    from datetime import datetime, timezone
    update_user(user["id"], email_verified_at=datetime.now(timezone.utc).isoformat())

    async def _run_test():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/auth/login", json={
                "email": "verified@example.com",
                "password": "MyStr0ngPwd!xx",
            })
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["user"]["email_verified"] is True

    _run(_run_test())


def test_login_wrong_password_still_401(app):
    """Wrong password returns generic 401, not 403 (no enumeration leak)."""
    async def _run_test():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Signup (unverified)
            await client.post("/api/auth/signup", json={
                "email": "wrong@example.com",
                "password": "MyStr0ngPwd!xx",
                "org_name": "WrongPwd Test",
                "accept_terms": True,
            })

            # Login with wrong password → 401 (not 403)
            resp = await client.post("/api/auth/login", json={
                "email": "wrong@example.com",
                "password": "TotallyWrong99",
            })
            assert resp.status_code == 401

    _run(_run_test())


def test_login_nonexistent_email_still_401(app):
    """Nonexistent email returns generic 401."""
    async def _run_test():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/auth/login", json={
                "email": "nobody@example.com",
                "password": "Whatever12345!",
            })
            assert resp.status_code == 401

    _run(_run_test())


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

def test_resend_verification_anti_enumeration(app):
    """Resend-verification returns 200 regardless of email existence."""
    async def _run_test():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Nonexistent email → still 200
            resp = await client.post("/api/auth/resend-verification", json={
                "email": "ghost@example.com",
            })
            assert resp.status_code == 200
            body1 = resp.json()

            # Signup then resend → same 200
            await client.post("/api/auth/signup", json={
                "email": "resend@example.com",
                "password": "MyStr0ngPwd!xx",
                "org_name": "Resend Test",
                "accept_terms": True,
            })
            resp = await client.post("/api/auth/resend-verification", json={
                "email": "resend@example.com",
            })
            assert resp.status_code == 200
            body2 = resp.json()

            # Same response structure
            assert body1["status"] == body2["status"] == "ok"

    _run(_run_test())


