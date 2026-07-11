"""H3 — Column locking: update_user and update_account reject unknown fields."""

from __future__ import annotations

import pytest

from loko.db.accounts import (
    create_account,
    create_user,
    update_account,
    update_user,
)


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


def test_update_user_rejects_injection():
    """Passing a crafted key like 'email=?, role' must raise ValueError."""
    account = create_account("Test Org")
    user = create_user(account["id"], "test@test.com", "strongpassword")
    with pytest.raises(ValueError, match="Invalid users field"):
        update_user(user["id"], **{"email=?, role": "x"})


def test_update_account_rejects_unknown_field():
    """Unknown field must raise ValueError."""
    account = create_account("Test Org")
    with pytest.raises(ValueError, match="Invalid accounts field"):
        update_account(account["id"], nonexistent="value")


def test_update_user_legitimate_fields():
    """Legitimate fields must work normally."""
    account = create_account("Test Org")
    user = create_user(account["id"], "test@test.com", "strongpassword")
    assert update_user(user["id"], last_login_at="2026-01-01T00:00:00Z")


def test_update_account_legitimate_fields():
    """Legitimate fields must work normally."""
    account = create_account("Test Org")
    assert update_account(account["id"], plan="standard", status="suspended")
