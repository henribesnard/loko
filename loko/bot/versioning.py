"""LOKO Bot — Publication versioning and rollback (Lot PRO-2 §7.2).

Each publication creates an immutable snapshot (release) with:
- config.json (full bot config)
- config_hash (SHA-256)
- model_hash (from classifier manifest)
- index_hash (knowledge base hash)

Rollback restores a previous release if the referenced model
is still present and verifies its hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_RELEASES = 10


class Release(BaseModel):
    """A publication release snapshot."""

    bot_id: str
    version: int
    created_at: str
    config_hash: str
    model_hash: str = ""
    index_hash: str = ""
    active: bool = True


class ReleaseStore:
    """SQLite-backed release store for publication versioning."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS releases (
                    bot_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    model_hash TEXT DEFAULT '',
                    index_hash TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    PRIMARY KEY (bot_id, version)
                )
            """)

    def create_release(
        self,
        bot_id: str,
        config_dict: dict[str, Any],
        model_hash: str = "",
        index_hash: str = "",
    ) -> Release:
        """Create a new release from the current config."""
        config_json = json.dumps(config_dict, sort_keys=True, ensure_ascii=False)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()

        with sqlite3.connect(self._db_path) as conn:
            # Get next version number
            row = conn.execute(
                "SELECT MAX(version) FROM releases WHERE bot_id = ?",
                (bot_id,),
            ).fetchone()
            next_version = (row[0] or 0) + 1

            # Deactivate previous releases
            conn.execute(
                "UPDATE releases SET active = 0 WHERE bot_id = ?",
                (bot_id,),
            )

            # Insert new release
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO releases (bot_id, version, created_at, config_json, "
                "config_hash, model_hash, index_hash, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    bot_id,
                    next_version,
                    now,
                    config_json,
                    config_hash,
                    model_hash,
                    index_hash,
                ),
            )

            # Enforce retention (FIFO, keep active + newest MAX_RELEASES)
            self._enforce_retention(conn, bot_id)

        return Release(
            bot_id=bot_id,
            version=next_version,
            created_at=now,
            config_hash=config_hash,
            model_hash=model_hash,
            index_hash=index_hash,
            active=True,
        )

    def list_releases(self, bot_id: str) -> list[Release]:
        """List all releases for a bot, newest first."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT bot_id, version, created_at, config_hash, model_hash, "
                "index_hash, active FROM releases WHERE bot_id = ? "
                "ORDER BY version DESC",
                (bot_id,),
            ).fetchall()

        return [
            Release(
                bot_id=r[0],
                version=r[1],
                created_at=r[2],
                config_hash=r[3],
                model_hash=r[4],
                index_hash=r[5],
                active=bool(r[6]),
            )
            for r in rows
        ]

    def get_release_config(self, bot_id: str, version: int) -> dict[str, Any] | None:
        """Get the config JSON for a specific release."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT config_json, config_hash FROM releases "
                "WHERE bot_id = ? AND version = ?",
                (bot_id, version),
            ).fetchone()

        if not row:
            return None

        config = json.loads(row[0])

        # Verify integrity
        actual_hash = hashlib.sha256(row[0].encode()).hexdigest()
        if actual_hash != row[1]:
            logger.error(
                "Release %s v%d config hash mismatch: expected=%s actual=%s",
                bot_id,
                version,
                row[1],
                actual_hash,
            )
            return None

        return config

    def activate_release(self, bot_id: str, version: int) -> bool:
        """Activate a specific release (deactivating others)."""
        with sqlite3.connect(self._db_path) as conn:
            # Check if release exists
            row = conn.execute(
                "SELECT version FROM releases WHERE bot_id = ? AND version = ?",
                (bot_id, version),
            ).fetchone()
            if not row:
                return False

            conn.execute(
                "UPDATE releases SET active = 0 WHERE bot_id = ?",
                (bot_id,),
            )
            conn.execute(
                "UPDATE releases SET active = 1 WHERE bot_id = ? AND version = ?",
                (bot_id, version),
            )
        return True

    def _enforce_retention(self, conn: sqlite3.Connection, bot_id: str) -> None:
        """Keep only MAX_RELEASES releases (FIFO, never delete active)."""
        rows = conn.execute(
            "SELECT version, active FROM releases WHERE bot_id = ? "
            "ORDER BY version DESC",
            (bot_id,),
        ).fetchall()

        if len(rows) <= MAX_RELEASES:
            return

        to_delete = []
        for version, active in rows[MAX_RELEASES:]:
            if not active:
                to_delete.append(version)

        for version in to_delete:
            conn.execute(
                "DELETE FROM releases WHERE bot_id = ? AND version = ?",
                (bot_id, version),
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

import os

_store: ReleaseStore | None = None


def get_release_store() -> ReleaseStore:
    """Get the global release store instance."""
    global _store
    if _store is None:
        db_dir = Path(os.environ.get("LOKO_DATA_DIR", "data"))
        db_dir.mkdir(parents=True, exist_ok=True)
        _store = ReleaseStore(db_dir / "loko_releases.db")
    return _store
