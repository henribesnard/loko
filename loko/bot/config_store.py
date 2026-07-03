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
    """Load a bot config from disk.  Returns None if not found."""
    config_path = get_bot_dir(bot_id) / "config.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return BotConfig.model_validate(data)
    except Exception:
        logger.exception("Failed to load bot config %s", config_path)
        return None


def list_bots() -> list[dict[str, str]]:
    """List all bots (id + name) found on disk."""
    bots_dir = get_bots_dir()
    result = []
    for bot_dir in sorted(bots_dir.iterdir()):
        config_path = bot_dir / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                result.append({
                    "bot_id": data.get("bot_id", bot_dir.name),
                    "name": data.get("name", ""),
                    "status": data.get("status", "draft"),
                })
            except Exception:
                continue
    return result


def delete_bot(bot_id: str) -> bool:
    """Delete a bot and all its data.  Returns True if found."""
    import shutil
    bot_dir = get_bot_dir(bot_id)
    if bot_dir.exists():
        shutil.rmtree(bot_dir)
        logger.info("Bot deleted: %s", bot_id)
        return True
    return False
