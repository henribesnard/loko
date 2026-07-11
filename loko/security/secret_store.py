"""LOKO Security — Encrypted secret store (Lot LLM §6.3).

Stores API keys encrypted with Fernet (AES-128-CBC + HMAC).
Master key derived from LOKO_SECRET_KEY env var (mandatory in server mode).

API:
    store = SecretStore(db_path)
    ref = store.put("sk-abc123...")
    plaintext = store.get(ref)
    store.delete(ref)

The plaintext never touches disk or logs.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_master_key() -> bytes:
    """Resolve master key from environment or desktop keyfile.

    Raises RuntimeError in server mode if LOKO_SECRET_KEY is not set
    (fail-closed, LLM-A8).
    """
    env_key = os.environ.get("LOKO_SECRET_KEY", "")
    if env_key:
        # Fernet requires 32 url-safe base64-encoded bytes.
        # If the env var is a raw passphrase, derive a proper key.
        from cryptography.fernet import Fernet
        import base64
        import hashlib

        # If it's already a valid Fernet key (44 chars base64), use it.
        if len(env_key) == 44:
            try:
                Fernet(env_key.encode())
                return env_key.encode()
            except Exception:
                pass

        # Otherwise derive from passphrase via SHA-256 → base64
        raw = hashlib.sha256(env_key.encode()).digest()
        return base64.urlsafe_b64encode(raw)

    # Desktop mode: generate and persist a key in ~/.loko/secret.key
    mode = os.environ.get("LOKO_MODE", "desktop")
    if mode == "server":
        raise RuntimeError(
            "LOKO_SECRET_KEY is required in server mode (fail-closed). "
            "Set the environment variable before starting the server."
        )

    from cryptography.fernet import Fernet

    key_path = Path.home() / ".loko" / "secret.key"
    if key_path.exists():
        return key_path.read_bytes().strip()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    # Best-effort permission restriction (Unix)
    try:
        key_path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass
    logger.info("Generated new secret key at %s", key_path)
    return key


class SecretStore:
    """Encrypted secret storage backed by SQLite + Fernet."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._fernet = None  # lazy init
        self._init_db()

    def _get_fernet(self):
        if self._fernet is None:
            from cryptography.fernet import Fernet

            key = _get_master_key()
            self._fernet = Fernet(key)
        return self._fernet

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS secrets (
                    ref TEXT PRIMARY KEY,
                    ciphertext BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    key_version INTEGER DEFAULT 1
                )
            """)

    def put(self, plaintext: str) -> str:
        """Encrypt and store a secret. Returns an opaque reference."""
        fernet = self._get_fernet()
        ref = f"ref_{uuid.uuid4().hex[:16]}"
        ciphertext = fernet.encrypt(plaintext.encode("utf-8"))
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO secrets (ref, ciphertext, created_at, key_version) "
                "VALUES (?, ?, ?, 1)",
                (ref, ciphertext, now),
            )
        return ref

    def get(self, ref: str) -> str:
        """Decrypt and return a secret by reference.

        Raises KeyError if ref not found, RuntimeError on decryption failure.
        """
        fernet = self._get_fernet()

        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT ciphertext FROM secrets WHERE ref = ?", (ref,)
            ).fetchone()

        if not row:
            raise KeyError(f"Secret ref not found: {ref}")

        try:
            plaintext = fernet.decrypt(row[0]).decode("utf-8")
        except Exception as exc:
            raise RuntimeError(f"Failed to decrypt secret {ref}") from exc

        # Update last_used_at
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE secrets SET last_used_at = ? WHERE ref = ?",
                (now, ref),
            )
        return plaintext

    def delete(self, ref: str) -> bool:
        """Delete a secret. Returns True if it existed."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("DELETE FROM secrets WHERE ref = ?", (ref,))
            return cursor.rowcount > 0

    def rotate(self, new_key: bytes) -> int:
        """Re-encrypt all secrets with a new master key.

        Returns the number of secrets rotated.
        """
        from cryptography.fernet import Fernet

        old_fernet = self._get_fernet()
        new_fernet = Fernet(new_key)
        count = 0

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT ref, ciphertext FROM secrets").fetchall()
            for ref, ciphertext in rows:
                try:
                    plaintext = old_fernet.decrypt(ciphertext)
                    new_ciphertext = new_fernet.encrypt(plaintext)
                    conn.execute(
                        "UPDATE secrets SET ciphertext = ?, key_version = key_version + 1 "
                        "WHERE ref = ?",
                        (new_ciphertext, ref),
                    )
                    count += 1
                except Exception:
                    logger.error("Failed to rotate secret %s — skipping", ref)

        # Update internal fernet to new key
        self._fernet = new_fernet
        logger.info("Rotated %d secrets", count)
        return count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    """Get the global secret store instance (lazy init)."""
    global _store
    if _store is None:
        db_dir = Path(os.environ.get("LOKO_DATA_DIR", "data"))
        db_dir.mkdir(parents=True, exist_ok=True)
        _store = SecretStore(db_dir / "loko_secrets.db")
    return _store
