"""LOKO Bot — Maintenance mode per bot (Lot PRO-7 §7.7).

When enabled, the runtime short-circuits all session creation and
messages with the ``maintenance`` template — a proper 200 response,
not an error. Active sessions receive the template then close.

State is persisted to disk so maintenance survives restarts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from loko.bot.session_store import get_bot_dir

logger = logging.getLogger(__name__)

_MAINTENANCE_FILE = "maintenance.json"

# In-memory cache: bot_id → {enabled, message_override}
_MAINTENANCE_STATE: dict[str, dict[str, Any]] = {}


def _state_path(bot_id: str) -> Path:
    """Path to the on-disk maintenance state file."""
    return get_bot_dir(bot_id) / _MAINTENANCE_FILE


def is_maintenance(bot_id: str) -> bool:
    """Check if a bot is in maintenance mode.

    Reads from in-memory cache first, falls back to disk.
    """
    # In-memory cache
    state = _MAINTENANCE_STATE.get(bot_id)
    if state is not None:
        return state.get("enabled", False)

    # Disk fallback
    state = _load_state(bot_id)
    if state:
        _MAINTENANCE_STATE[bot_id] = state
        return state.get("enabled", False)

    return False


def get_maintenance_message(bot_id: str) -> str | None:
    """Get the custom maintenance message override, if any."""
    state = _MAINTENANCE_STATE.get(bot_id)
    if state is None:
        state = _load_state(bot_id) or {}
        _MAINTENANCE_STATE[bot_id] = state
    return state.get("message_override") or None


def set_maintenance(
    bot_id: str,
    enabled: bool,
    message_override: str | None = None,
) -> dict[str, Any]:
    """Enable or disable maintenance mode for a bot.

    Returns the updated state dict.
    """
    state = {
        "enabled": enabled,
        "message_override": message_override or "",
    }
    _MAINTENANCE_STATE[bot_id] = state
    _persist_state(bot_id, state)

    logger.info(
        "Maintenance mode %s for bot %s%s",
        "enabled" if enabled else "disabled",
        bot_id,
        f" (custom message)" if message_override else "",
    )

    return state


def _load_state(bot_id: str) -> dict[str, Any] | None:
    """Read maintenance state from disk."""
    try:
        path = _state_path(bot_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _persist_state(bot_id: str, state: dict[str, Any]) -> None:
    """Write maintenance state to disk."""
    try:
        path = _state_path(bot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Could not persist maintenance state for bot %s", bot_id)
