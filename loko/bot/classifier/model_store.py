"""LOKO Bot — SetFit model persistence.

Models are saved per bot under:
  ~/.loko/bots/{bot_id}/models/level1/
  ~/.loko/bots/{bot_id}/models/level2_{intent_id}/
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from loko.bot.session_store import get_bot_dir

logger = logging.getLogger(__name__)


def get_model_dir(bot_id: str, level: str, intent_id: str | None = None) -> Path:
    """Return the directory for a classifier model.

    Parameters
    ----------
    bot_id : str
    level : str
        "level1" or "level2"
    intent_id : str | None
        Required when level is "level2".
    """
    from loko.bot.models import validate_slug

    if intent_id is not None:
        validate_slug(intent_id, "intent_id")

    base = get_bot_dir(bot_id) / "models"
    if level == "level1":
        model_dir = base / "level1"
    elif level == "level2" and intent_id:
        model_dir = base / f"level2_{intent_id}"
    else:
        raise ValueError(f"Invalid level/intent_id: {level}/{intent_id}")
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


def model_exists(bot_id: str, level: str, intent_id: str | None = None) -> bool:
    """Check if a trained model exists on disk."""
    model_dir = get_model_dir(bot_id, level, intent_id)
    # SetFit saves a config.json in the model directory
    return (model_dir / "config.json").exists()


def delete_model(bot_id: str, level: str, intent_id: str | None = None) -> None:
    """Delete a model from disk."""
    model_dir = get_model_dir(bot_id, level, intent_id)
    if model_dir.exists():
        shutil.rmtree(model_dir)
        logger.info("Deleted model at %s", model_dir)


def list_models(bot_id: str) -> list[dict[str, str]]:
    """List all trained models for a bot."""
    base = get_bot_dir(bot_id) / "models"
    if not base.exists():
        return []
    result = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "config.json").exists():
            result.append({"name": d.name, "path": str(d)})
    return result
