"""S1 — Verify that tokens are never logged during signup or reset."""

from __future__ import annotations

import logging
import os
from unittest import mock

import pytest

from loko.db.accounts import create_account, create_user, create_email_token


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    import loko.db.accounts as mod
    monkeypatch.setattr(mod, "_DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(mod, "_connection", None)
    yield
    if mod._connection:
        mod._connection.close()
        mod._connection = None


def test_signup_no_token_in_logs(caplog):
    """Signup must not log the verification token."""
    from httpx import ASGITransport, AsyncClient
    import asyncio

    # Set up env — no debug tokens
    env = {"LOKO_MODE": "desktop"}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LOKO_AUTH_DEBUG_TOKENS", None)

        from loko.main import create_app
        app = create_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                with caplog.at_level(logging.DEBUG):
                    resp = await client.post("/api/auth/signup", json={
                        "email": "s1test@example.com",
                        "password": "MyStr0ngPwd!",
                        "org_name": "S1 Test",
                        "accept_terms": True,
                    })
                    assert resp.status_code == 201
                    # No _debug_verify_token in response (debug mode off)
                    assert "_debug_verify_token" not in resp.json()

            # Check no token value in logs
            for record in caplog.records:
                msg = record.getMessage()
                # Should never see a raw token (base64 urlsafe, 43+ chars)
                # The log should only say "verify_token created"
                assert "Verify token for" not in msg, f"Token leaked in log: {msg}"

        asyncio.get_event_loop().run_until_complete(_run())


def test_reset_no_token_in_logs(caplog):
    """Request-reset must not log the reset token."""
    # Pre-create a user
    account = create_account("ResetOrg")
    create_user(account["id"], "reset@example.com", "OldPassword1")

    from httpx import ASGITransport, AsyncClient
    import asyncio

    from loko.main import create_app
    app = create_app()

    async def _run():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with caplog.at_level(logging.DEBUG):
                resp = await client.post("/api/auth/request-reset", json={
                    "email": "reset@example.com",
                })
                assert resp.status_code == 200

        for record in caplog.records:
            msg = record.getMessage()
            assert "Reset token for" not in msg, f"Token leaked in log: {msg}"

    asyncio.get_event_loop().run_until_complete(_run())
