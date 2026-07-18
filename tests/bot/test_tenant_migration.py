"""T1 — Tenant migration: account_id on BotConfig, lazy migration, idempotence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def bots_dir(tmp_path, monkeypatch):
    """Set up a temporary bots directory."""
    data_dir = tmp_path / "data"
    bots = data_dir / "bots"
    bots.mkdir(parents=True)

    # Patch LOKO_DATA_DIR env var so get_bots_dir() uses tmp_path
    monkeypatch.setenv("LOKO_DATA_DIR", str(data_dir))

    # Patch accounts db
    import loko.db.accounts as acc

    monkeypatch.setattr(acc, "_DB_PATH", data_dir / "loko_accounts.db")
    monkeypatch.setattr(acc, "_connection", None)

    yield bots

    if acc._connection:
        acc._connection.close()
        acc._connection = None


def _create_bot_v1(bots_dir: Path, bot_id: str, name: str) -> Path:
    """Create a bot config without account_id (schema v1)."""
    bot_dir = bots_dir / bot_id
    bot_dir.mkdir()
    config = {
        "schema_version": 1,
        "bot_id": bot_id,
        "name": name,
        "status": "draft",
        "intents": [],
    }
    config_path = bot_dir / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def _create_bot_v2(bots_dir: Path, bot_id: str, name: str, account_id: str) -> Path:
    """Create a bot config with account_id (schema v2)."""
    bot_dir = bots_dir / bot_id
    bot_dir.mkdir()
    config = {
        "schema_version": 2,
        "bot_id": bot_id,
        "name": name,
        "account_id": account_id,
        "status": "draft",
        "intents": [],
    }
    config_path = bot_dir / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def test_lazy_migration_assigns_internal_account(bots_dir):
    """Bot without account_id gets migrated to internal account on load."""
    from loko.bot.config_store import load_bot_config

    _create_bot_v1(bots_dir, "bot-a", "Bot A")
    config = load_bot_config("bot-a")

    assert config is not None
    assert config.account_id == "wezon-internal"
    assert config.schema_version == 4

    # Verify persisted
    data = json.loads((bots_dir / "bot-a" / "config.json").read_text(encoding="utf-8"))
    assert data["account_id"] == "wezon-internal"
    assert data["schema_version"] == 4


def test_existing_v2_bot_unchanged(bots_dir):
    """Bot already on v2 with account_id is not re-migrated."""
    from loko.bot.config_store import load_bot_config

    _create_bot_v2(bots_dir, "bot-b", "Bot B", "my-account")
    config = load_bot_config("bot-b")

    assert config is not None
    assert config.account_id == "my-account"


def test_migration_idempotent(bots_dir):
    """Running migration twice produces the same result."""
    from loko.bot.config_store import load_bot_config

    _create_bot_v1(bots_dir, "bot-c", "Bot C")

    config1 = load_bot_config("bot-c")
    data1 = json.loads((bots_dir / "bot-c" / "config.json").read_text(encoding="utf-8"))

    config2 = load_bot_config("bot-c")
    data2 = json.loads((bots_dir / "bot-c" / "config.json").read_text(encoding="utf-8"))

    assert data1 == data2
    assert config1.account_id == config2.account_id


def test_list_bots_returns_account_id(bots_dir):
    """list_bots() includes account_id for all bots."""
    from loko.bot.config_store import list_bots

    _create_bot_v2(bots_dir, "bot-d", "Bot D", "acct-1")
    _create_bot_v2(bots_dir, "bot-e", "Bot E", "acct-2")

    bots = list_bots()
    assert len(bots) == 2
    assert all("account_id" in b for b in bots)


def test_list_bots_filters_by_account(bots_dir):
    """list_bots(account_id=X) returns only bots belonging to X."""
    from loko.bot.config_store import list_bots

    _create_bot_v2(bots_dir, "bot-f", "Bot F", "acct-1")
    _create_bot_v2(bots_dir, "bot-g", "Bot G", "acct-2")

    bots = list_bots(account_id="acct-1")
    assert len(bots) == 1
    assert bots[0]["bot_id"] == "bot-f"
