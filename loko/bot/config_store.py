"""LOKO Bot — Bot configuration persistence.

Each bot's config is stored as JSON at
~/.loko/bots/{bot_id}/config.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from loko.bot.models import BotConfig
from loko.bot.session_store import get_bot_dir, get_bots_dir

logger = logging.getLogger(__name__)


def save_bot_config(config: BotConfig) -> Path:
    """Persist a bot config to disk.  Returns the file path."""
    bot_dir = get_bot_dir(config.bot_id)
    config_path = bot_dir / "config.json"
    config_path.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Bot config saved: %s", config_path)
    return config_path


def load_bot_config(bot_id: str) -> BotConfig | None:
    """Load a bot config from disk.  Returns None if not found.

    T1: lazy migration — if schema_version < 2 or account_id missing,
    the bot is assigned to the internal account and persisted.
    """
    config_path = get_bot_dir(bot_id, create=False) / "config.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        config = BotConfig.model_validate(data)
        # T1: lazy migration for schema v1 → v2
        if data.get("schema_version", 1) < 2 or not config.account_id:
            config = config.model_copy(update={
                "schema_version": 2,
                "account_id": config.account_id or _get_internal_account_id(),
            })
            save_bot_config(config)
            logger.info("Bot %s migrated to schema v2 (account_id=%s)", bot_id, config.account_id)
        return config
    except Exception:
        logger.exception("Failed to load bot config %s", config_path)
        return None


# T1: Internal account for legacy bots
_INTERNAL_ACCOUNT_ID = "wezon-internal"


def _get_internal_account_id() -> str:
    """Return the internal account ID, creating it if needed."""
    from loko.db.accounts import get_account, get_db
    try:
        account = get_account(_INTERNAL_ACCOUNT_ID)
        if account:
            return _INTERNAL_ACCOUNT_ID
        # Create with fixed ID
        db = get_db()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO accounts (id, org_name, plan, quotas, status, created_at) "
            "VALUES (?, ?, 'internal', '{}', 'active', ?)",
            (_INTERNAL_ACCOUNT_ID, "Wezon interne", now),
        )
        db.commit()
        return _INTERNAL_ACCOUNT_ID
    except Exception:
        logger.warning("Could not create internal account, using fallback ID")
        return _INTERNAL_ACCOUNT_ID


def list_bots(account_id: str | None = None) -> list[dict[str, str]]:
    """List all bots found on disk. If account_id given, filter by tenant."""
    bots_dir = get_bots_dir()
    result = []
    for bot_dir in sorted(bots_dir.iterdir()):
        config_path = bot_dir / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                bot_account = data.get("account_id", "")
                if account_id and bot_account != account_id:
                    continue
                result.append({
                    "bot_id": data.get("bot_id", bot_dir.name),
                    "name": data.get("name", ""),
                    "status": data.get("status", "draft"),
                    "account_id": bot_account,
                })
            except Exception:
                continue
    return result


def delete_bot(bot_id: str) -> bool:
    """Delete a bot and all its data.  Returns True if found."""
    import shutil
    bot_dir = get_bot_dir(bot_id, create=False)
    if bot_dir.exists():
        shutil.rmtree(bot_dir)
        logger.info("Bot deleted: %s", bot_id)
        return True
    return False
