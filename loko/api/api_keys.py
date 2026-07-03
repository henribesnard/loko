"""LOKO Bot — Scoped API key management.

Provides API key generation, validation, and middleware for
bot-scoped authentication.

Keys are stored as SHA-256 hashes alongside their bot scope
and allowed origins.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any

from loko.bot.session_store import get_bots_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key data model
# ---------------------------------------------------------------------------

class APIKeyRecord:
    """Represents a stored API key record."""

    def __init__(
        self,
        key_id: str,
        key_hash: str,
        bot_id: str,
        label: str = "",
        allowed_origins: list[str] | None = None,
        created_at: str = "",
    ):
        self.key_id = key_id
        self.key_hash = key_hash
        self.bot_id = bot_id
        self.label = label
        self.allowed_origins = allowed_origins or []
        self.created_at = created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "bot_id": self.bot_id,
            "label": self.label,
            "allowed_origins": self.allowed_origins,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIKeyRecord:
        return cls(**data)


# ---------------------------------------------------------------------------
# Key store (file-based, per bot)
# ---------------------------------------------------------------------------

def _keys_file(bot_id: str) -> Path:
    return get_bots_dir() / bot_id / "api_keys.json"


def _load_keys(bot_id: str) -> list[APIKeyRecord]:
    path = _keys_file(bot_id)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [APIKeyRecord.from_dict(r) for r in data]


def _save_keys(bot_id: str, records: list[APIKeyRecord]) -> None:
    path = _keys_file(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_api_key(
    bot_id: str,
    label: str = "",
    allowed_origins: list[str] | None = None,
) -> tuple[str, str]:
    """Generate a new API key for a bot.

    Returns
    -------
    tuple[str, str]
        (raw_key, key_id) — the raw key is returned only once.
    """
    from datetime import datetime, timezone

    raw_key = f"loko_{secrets.token_urlsafe(32)}"
    key_id = str(uuid.uuid4())
    key_hash = _hash_key(raw_key)

    record = APIKeyRecord(
        key_id=key_id,
        key_hash=key_hash,
        bot_id=bot_id,
        label=label,
        allowed_origins=allowed_origins or [],
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    keys = _load_keys(bot_id)
    keys.append(record)
    _save_keys(bot_id, keys)

    logger.info("Generated API key %s for bot %s", key_id, bot_id)
    return raw_key, key_id


def validate_api_key(raw_key: str) -> APIKeyRecord | None:
    """Validate a raw API key and return the associated record.

    Searches across all bots.  Returns None if invalid.
    """
    key_hash = _hash_key(raw_key)
    bots_dir = get_bots_dir()

    if not bots_dir.exists():
        return None

    for bot_dir in bots_dir.iterdir():
        if not bot_dir.is_dir():
            continue
        keys = _load_keys(bot_dir.name)
        for record in keys:
            if record.key_hash == key_hash:
                return record

    return None


def validate_api_key_for_bot(raw_key: str, bot_id: str) -> APIKeyRecord | None:
    """Validate a raw API key for a specific bot."""
    key_hash = _hash_key(raw_key)
    keys = _load_keys(bot_id)

    for record in keys:
        if record.key_hash == key_hash:
            return record

    return None


def list_api_keys(bot_id: str) -> list[dict[str, Any]]:
    """List all API keys for a bot (without hashes)."""
    keys = _load_keys(bot_id)
    return [
        {
            "key_id": r.key_id,
            "bot_id": r.bot_id,
            "label": r.label,
            "allowed_origins": r.allowed_origins,
            "created_at": r.created_at,
        }
        for r in keys
    ]


def revoke_api_key(bot_id: str, key_id: str) -> bool:
    """Revoke (delete) an API key.  Returns True if found and deleted."""
    keys = _load_keys(bot_id)
    initial_count = len(keys)
    keys = [k for k in keys if k.key_id != key_id]

    if len(keys) < initial_count:
        _save_keys(bot_id, keys)
        logger.info("Revoked API key %s for bot %s", key_id, bot_id)
        return True

    return False


def check_origin(record: APIKeyRecord, origin: str | None) -> bool:
    """Check if an origin is allowed for this API key."""
    if not record.allowed_origins:
        return True  # no origin restriction
    if not origin:
        return False
    return origin in record.allowed_origins
