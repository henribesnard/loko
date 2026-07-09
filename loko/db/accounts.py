"""LOKO — Account database (SQLite).

Handles: accounts, users, sessions, email_tokens.
All functions are synchronous (sqlite3); call from FastAPI via run_in_executor.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.environ.get("LOKO_DATA_DIR", "data"))
_DB_PATH = _DATA_DIR / "loko_accounts.db"

_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """Return a module-level SQLite connection (lazy-init)."""
    global _connection
    if _connection is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
        _init_schema(_connection)
    return _connection


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            org_name TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'trial',
            quotas TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified_at TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            role TEXT NOT NULL DEFAULT 'owner'
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS email_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL,
            type TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, 600k iterations)
# ---------------------------------------------------------------------------

_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 + random salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _HASH_ITERATIONS)
    return f"pbkdf2:sha256:{_HASH_ITERATIONS}:{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        parts = stored_hash.split(":")
        iterations = int(parts[2])
        salt = parts[3]
        expected = parts[4]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), expected)
    except (IndexError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

def create_account(org_name: str) -> dict[str, Any]:
    """Create a new account. Returns the account dict."""
    db = get_db()
    account_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO accounts (id, org_name, plan, quotas, status, created_at) VALUES (?, ?, 'trial', '{}', 'active', ?)",
        (account_id, org_name, now),
    )
    db.commit()
    return {"id": account_id, "org_name": org_name, "plan": "trial", "status": "active", "created_at": now}


def get_account(account_id: str) -> dict[str, Any] | None:
    """Get an account by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def list_accounts() -> list[dict[str, Any]]:
    """List all accounts (ops)."""
    db = get_db()
    rows = db.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_account(account_id: str, **kwargs: Any) -> bool:
    """Update account fields."""
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [account_id]
    db.execute(f"UPDATE accounts SET {sets} WHERE id = ?", vals)
    db.commit()
    return db.total_changes > 0


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(account_id: str, email: str, password: str) -> dict[str, Any]:
    """Create a new user. Returns the user dict (without password_hash)."""
    db = get_db()
    user_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password(password)
    db.execute(
        "INSERT INTO users (id, account_id, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?, 'owner')",
        (user_id, account_id, email, pw_hash, now),
    )
    db.commit()
    return {"id": user_id, "account_id": account_id, "email": email, "created_at": now, "role": "owner"}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Get a user by email (includes password_hash for verification)."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Get a user by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_user(user_id: str, **kwargs: Any) -> bool:
    """Update user fields."""
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    db.execute(f"UPDATE users SET {sets} WHERE id = ?", vals)
    db.commit()
    return db.total_changes > 0


def delete_user_and_account(user_id: str, account_id: str) -> bool:
    """Delete user, account, and all related data."""
    db = get_db()
    db.execute("DELETE FROM email_tokens WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_SESSION_DURATION_DAYS = 7


def create_session(user_id: str) -> str:
    """Create a new session. Returns the session token (opaque, 128-bit hex)."""
    db = get_db()
    session_id = secrets.token_hex(16)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=_SESSION_DURATION_DAYS)
    db.execute(
        "INSERT INTO sessions (id, user_id, created_at, expires_at, revoked) VALUES (?, ?, ?, ?, 0)",
        (session_id, user_id, now.isoformat(), expires.isoformat()),
    )
    db.commit()
    return session_id


def validate_session(session_id: str) -> dict[str, Any] | None:
    """Validate a session token. Returns user + account info if valid, None otherwise."""
    db = get_db()
    row = db.execute(
        """SELECT s.*, u.email, u.account_id, u.role, a.org_name, a.plan, a.status AS account_status
           FROM sessions s
           JOIN users u ON s.user_id = u.id
           JOIN accounts a ON u.account_id = a.id
           WHERE s.id = ? AND s.revoked = 0""",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    # Check expiry
    expires = datetime.fromisoformat(data["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        return None
    # Check account not suspended
    if data.get("account_status") == "suspended":
        return None
    return data


def revoke_session(session_id: str) -> bool:
    """Revoke a session."""
    db = get_db()
    db.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (session_id,))
    db.commit()
    return db.total_changes > 0


def revoke_all_sessions(user_id: str) -> int:
    """Revoke all sessions for a user."""
    db = get_db()
    db.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))
    db.commit()
    return db.total_changes


# ---------------------------------------------------------------------------
# Email tokens (verification, password reset)
# ---------------------------------------------------------------------------

_EMAIL_TOKEN_EXPIRY_HOURS = 24


def create_email_token(user_id: str, token_type: str) -> str:
    """Create an email token. Returns the raw token (to be sent via email)."""
    db = get_db()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_id = str(uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=_EMAIL_TOKEN_EXPIRY_HOURS)
    db.execute(
        "INSERT INTO email_tokens (id, user_id, token_hash, type, expires_at) VALUES (?, ?, ?, ?, ?)",
        (token_id, user_id, token_hash, token_type, expires.isoformat()),
    )
    db.commit()
    return raw_token


def validate_email_token(raw_token: str, token_type: str) -> dict[str, Any] | None:
    """Validate an email token. Returns token+user info if valid."""
    db = get_db()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = db.execute(
        """SELECT et.*, u.email, u.account_id
           FROM email_tokens et
           JOIN users u ON et.user_id = u.id
           WHERE et.token_hash = ? AND et.type = ? AND et.used_at IS NULL""",
        (token_hash, token_type),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    expires = datetime.fromisoformat(data["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        return None
    return data


def mark_token_used(token_id: str) -> None:
    """Mark an email token as used."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE email_tokens SET used_at = ? WHERE id = ?", (now, token_id))
    db.commit()
