"""T5 — CI permanent: cross-account access must be rejected.

P0-10 requirement: no user from account A can read/write/delete
a bot belonging to account B.
"""

from __future__ import annotations

import json

import pytest

from loko.bot.models import BotConfig
from loko.db.accounts import (
    create_account,
    create_session,
    create_user,
)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Set up a 2-account environment with one bot each."""
    data_dir = tmp_path / "data"
    bots = data_dir / "bots"
    bots.mkdir(parents=True)

    monkeypatch.setenv("LOKO_DATA_DIR", str(data_dir))

    import loko.db.accounts as acc
    monkeypatch.setattr(acc, "_DB_PATH", data_dir / "loko_accounts.db")
    monkeypatch.setattr(acc, "_connection", None)

    # Create two accounts
    acct_a = create_account("Account A")
    acct_b = create_account("Account B")

    user_a = create_user(acct_a["id"], "alice@a.com", "StrongPass1!")
    user_b = create_user(acct_b["id"], "bob@b.com", "StrongPass2!")

    session_a = create_session(user_a["id"])
    session_b = create_session(user_b["id"])

    # Create bot for account A
    bot_dir_a = bots / "bot-a"
    bot_dir_a.mkdir()
    config_a = BotConfig(bot_id="bot-a", name="Bot A", account_id=acct_a["id"])
    (bot_dir_a / "config.json").write_text(
        json.dumps(config_a.model_dump(mode="json")),
        encoding="utf-8",
    )

    # Create bot for account B
    bot_dir_b = bots / "bot-b"
    bot_dir_b.mkdir()
    config_b = BotConfig(bot_id="bot-b", name="Bot B", account_id=acct_b["id"])
    (bot_dir_b / "config.json").write_text(
        json.dumps(config_b.model_dump(mode="json")),
        encoding="utf-8",
    )

    yield {
        "acct_a": acct_a, "acct_b": acct_b,
        "user_a": user_a, "user_b": user_b,
        "session_a": session_a, "session_b": session_b,
    }

    if acc._connection:
        acc._connection.close()
        acc._connection = None


def test_user_a_can_read_own_bot(env):
    """User A can read bot-a."""
    from loko.api.session_middleware import require_tenant_or_ops
    from unittest.mock import MagicMock
    import asyncio

    request = MagicMock()
    request.cookies = {"loko_session": env["session_a"]}
    request.headers = {}
    request.state = MagicMock()

    result = asyncio.get_event_loop().run_until_complete(
        require_tenant_or_ops(request, "bot-a")
    )
    assert result is not None
    assert result["account_id"] == env["acct_a"]["id"]


def test_user_b_cannot_read_bot_a(env):
    """User B must get 404 when trying to read bot-a (not 403)."""
    from loko.api.session_middleware import require_tenant_or_ops
    from fastapi import HTTPException
    from unittest.mock import MagicMock
    import asyncio

    request = MagicMock()
    request.cookies = {"loko_session": env["session_b"]}
    request.headers = {}
    request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            require_tenant_or_ops(request, "bot-a")
        )

    # Must be 404 (not 403) to avoid enumeration
    assert exc_info.value.status_code == 404


def test_list_bots_scoped(env):
    """list_bots(account_id) only returns that account's bots."""
    from loko.bot.config_store import list_bots

    bots_a = list_bots(account_id=env["acct_a"]["id"])
    bots_b = list_bots(account_id=env["acct_b"]["id"])

    assert len(bots_a) == 1
    assert bots_a[0]["bot_id"] == "bot-a"

    assert len(bots_b) == 1
    assert bots_b[0]["bot_id"] == "bot-b"


def test_no_session_returns_401(env):
    """No session cookie must return 401."""
    from loko.api.session_middleware import require_tenant_or_ops
    from fastapi import HTTPException
    from unittest.mock import MagicMock
    import asyncio

    request = MagicMock()
    request.cookies = {}
    request.headers = {}
    request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            require_tenant_or_ops(request, "bot-a")
        )

    assert exc_info.value.status_code == 401
