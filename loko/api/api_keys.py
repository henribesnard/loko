"""LOKO Bot — Scoped API key management.

Provides API key generation, validation, and middleware for
bot-scoped authentication.

Keys are stored as SHA-256 hashes alongside their bot scope
and allowed origins.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
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
        expires_at: str | None = None,  # K3: for rotation grace period
        superseded_by: str | None = None,  # K3: key_id that replaced this one
        environment: str = "live",  # PRO-3: "test" or "live"
    ):
        self.key_id = key_id
        self.key_hash = key_hash
        self.bot_id = bot_id
        self.label = label
        self.allowed_origins = allowed_origins or []
        self.created_at = created_at
        self.expires_at = expires_at
        self.superseded_by = superseded_by
        self.environment = environment

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "bot_id": self.bot_id,
            "label": self.label,
            "allowed_origins": self.allowed_origins,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "superseded_by": self.superseded_by,
            "environment": self.environment,
        }

    @property
    def is_test(self) -> bool:
        """PRO-3: check if this is a test key."""
        return self.environment == "test"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIKeyRecord:
        return cls(**data)

    def is_expired(self) -> bool:
        """Check if this key is expired (K3)."""
        if not self.expires_at:
            return False

        from datetime import datetime, timezone

        expires = datetime.fromisoformat(self.expires_at)
        now = datetime.now(timezone.utc)
        return now > expires


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
    environment: str = "live",
) -> tuple[str, str]:
    """Generate a new API key for a bot.

    Parameters
    ----------
    bot_id : str
        Bot identifier.
    label : str
        Human-readable label.
    allowed_origins : list[str] | None
        CORS-allowed origins for this key.
    environment : str
        PRO-3: "test" or "live" — determines key prefix.

    Returns
    -------
    tuple[str, str]
        (raw_key, key_id) — the raw key is returned only once.
    """
    from datetime import datetime, timezone

    # PRO-3: use distinct prefix for test vs live keys
    prefix = "loko_test_" if environment == "test" else "loko_live_"
    raw_key = f"{prefix}{secrets.token_urlsafe(32)}"
    key_id = str(uuid.uuid4())
    key_hash = _hash_key(raw_key)

    record = APIKeyRecord(
        key_id=key_id,
        key_hash=key_hash,
        bot_id=bot_id,
        label=label,
        allowed_origins=allowed_origins or [],
        created_at=datetime.now(timezone.utc).isoformat(),
        environment=environment,
    )

    keys = _load_keys(bot_id)
    keys.append(record)
    _save_keys(bot_id, keys)

    logger.info("Generated %s API key %s for bot %s", environment, key_id, bot_id)
    return raw_key, key_id


def validate_api_key(raw_key: str) -> APIKeyRecord | None:
    """Validate a raw API key and return the associated record.

    Searches across all bots.  Returns None if invalid or expired (K3).
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
            if _hmac.compare_digest(record.key_hash, key_hash):
                # K3: Reject expired keys
                if record.is_expired():
                    logger.warning("API key %s is expired", record.key_id)
                    return None
                return record

    return None


def validate_api_key_for_bot(raw_key: str, bot_id: str) -> APIKeyRecord | None:
    """Validate a raw API key for a specific bot.

    Returns None if key is invalid or expired (K3).
    """
    key_hash = _hash_key(raw_key)
    keys = _load_keys(bot_id)

    for record in keys:
        if _hmac.compare_digest(record.key_hash, key_hash):
            # K3: Reject expired keys
            if record.is_expired():
                logger.warning(
                    "API key %s is expired for bot %s", record.key_id, bot_id
                )
                return None
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
            "expires_at": r.expires_at,  # K3: expose expiration
            "superseded_by": r.superseded_by,  # K3: show if rotated
            "is_expired": r.is_expired(),  # K3: computed flag
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


def rotate_api_key(
    bot_id: str,
    old_key_id: str,
    grace_period_hours: int = 24,
) -> tuple[str, str] | None:
    """Rotate an API key (K3).

    Creates a new key and marks the old one to expire after grace period.
    During grace period, both keys are valid.

    Args:
        bot_id: Bot ID
        old_key_id: Key ID to rotate
        grace_period_hours: Hours before old key expires (default 24)

    Returns:
        (new_raw_key, new_key_id) or None if old key not found
    """
    from datetime import datetime, timezone, timedelta

    keys = _load_keys(bot_id)

    # Find old key
    old_key = None
    for k in keys:
        if k.key_id == old_key_id:
            old_key = k
            break

    if not old_key:
        return None

    # Generate new key (inherit label and origins)
    new_raw_key, new_key_id = generate_api_key(
        bot_id=bot_id,
        label=old_key.label,
        allowed_origins=old_key.allowed_origins,
    )

    # Mark old key as expiring
    expires_at = datetime.now(timezone.utc) + timedelta(hours=grace_period_hours)
    old_key.expires_at = expires_at.isoformat()
    old_key.superseded_by = new_key_id

    # Save updated old key
    keys = _load_keys(bot_id)  # Reload to include new key
    for k in keys:
        if k.key_id == old_key_id:
            k.expires_at = old_key.expires_at
            k.superseded_by = old_key.superseded_by
            break

    _save_keys(bot_id, keys)

    logger.info(
        "Rotated API key %s for bot %s → new key %s (old expires in %dh)",
        old_key_id,
        bot_id,
        new_key_id,
        grace_period_hours,
    )

    return new_raw_key, new_key_id


def cleanup_expired_keys(bot_id: str | None = None) -> int:
    """Remove expired API keys (K3).

    Args:
        bot_id: If specified, only clean keys for this bot.
                If None, clean all bots.

    Returns:
        Number of keys deleted
    """
    deleted_count = 0

    if bot_id:
        bot_ids = [bot_id]
    else:
        # Clean all bots
        bots_dir = get_bots_dir()
        if not bots_dir.exists():
            return 0
        bot_ids = [d.name for d in bots_dir.iterdir() if d.is_dir()]

    for bid in bot_ids:
        keys = _load_keys(bid)
        initial_count = len(keys)

        # Filter out expired keys
        keys = [k for k in keys if not k.is_expired()]

        deleted = initial_count - len(keys)
        if deleted > 0:
            _save_keys(bid, keys)
            logger.info("Cleaned up %d expired keys for bot %s", deleted, bid)
            deleted_count += deleted

    return deleted_count


def check_origin(record: APIKeyRecord, origin: str | None) -> bool:
    """Check if an origin is allowed for this API key.

    Policy (fail-closed):
    - allowed_origins=[] → reject cross-origin (no origin header = OK, e.g. server-to-server).
    - allowed_origins=["*"] → allow all origins.
    - allowed_origins=["https://a.com"] → only that origin.
    - If origin header is absent (non-browser request) → allowed.
    """
    # Non-browser requests (no Origin header) are always allowed
    if not origin:
        return True

    # Explicit wildcard allows everything
    if "*" in record.allowed_origins:
        return True

    # Empty list = no cross-origin allowed (fail-closed)
    if not record.allowed_origins:
        return False

    return origin in record.allowed_origins
