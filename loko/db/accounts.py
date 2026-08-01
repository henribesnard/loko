"""LOKO — Account database (SQLite).

Handles: accounts, users, sessions, email_tokens, memberships, invitations.
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

        CREATE TABLE IF NOT EXISTS memberships (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            UNIQUE(account_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS invitations (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            token_hash TEXT NOT NULL,
            invited_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_memberships_account ON memberships(account_id);
        CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
        CREATE INDEX IF NOT EXISTS idx_invitations_account ON invitations(account_id);
        CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token_hash);
    """)
    conn.commit()
    _migrate_add_columns(conn)
    _migrate_existing_users_to_memberships(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add new columns via ALTER TABLE (idempotent)."""
    # User profile columns
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "display_name" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if "language" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'fr'")
    if "timezone" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Europe/Paris'")
    # Session metadata columns
    sess_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "user_agent" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''")
    if "ip_address" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN ip_address TEXT NOT NULL DEFAULT ''")
    conn.commit()


def _migrate_existing_users_to_memberships(conn: sqlite3.Connection) -> None:
    """One-time migration: create membership rows for all existing users (AC-4)."""
    count = conn.execute("SELECT COUNT(*) FROM memberships").fetchone()[0]
    if count > 0:
        return  # Already migrated
    users = conn.execute("SELECT id, account_id, role FROM users").fetchall()
    if not users:
        return
    now = datetime.now(timezone.utc).isoformat()
    for user in users:
        conn.execute(
            "INSERT OR IGNORE INTO memberships (id, account_id, user_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), user[1], user[0], user[2] or "owner", now),
        )
    conn.commit()
    logger.info("Migrated %d existing users to memberships table", len(users))


# ---------------------------------------------------------------------------
# Password hashing — S3: argon2id preferred, PBKDF2 fallback (AR-2)
# ---------------------------------------------------------------------------

_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """S3: Hash with argon2id if available, else PBKDF2-HMAC-SHA256 (AR-2)."""
    try:
        from argon2 import PasswordHasher

        ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
        return ph.hash(password)
    except ImportError:
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), _HASH_ITERATIONS
        )
        return f"pbkdf2:sha256:{_HASH_ITERATIONS}:{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """S3: Verify password — supports both argon2id and PBKDF2 hashes."""
    # Argon2id hashes start with $argon2id$
    if stored_hash.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError

            ph = PasswordHasher()
            return ph.verify(stored_hash, password)
        except (ImportError, VerifyMismatchError):
            return False
        except Exception as exc:
            logging.getLogger(__name__).warning("Password verification error: %s", exc)
            return False

    # Legacy PBKDF2
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
# H3: Column allowlists (prevent SQL injection via kwargs keys)
# ---------------------------------------------------------------------------

_ACCOUNT_FIELDS = frozenset({"org_name", "plan", "quotas", "status"})
_USER_FIELDS = frozenset(
    {
        "email",
        "password_hash",
        "email_verified_at",
        "last_login_at",
        "role",
        "terms_accepted_version",
        "terms_accepted_at",
        "display_name",
        "language",
        "timezone",
    }
)


def _validate_fields(kwargs: dict, allowed: frozenset[str], table: str) -> None:
    """Raise ValueError if any key is not in the allowlist."""
    bad = set(kwargs.keys()) - allowed
    if bad:
        raise ValueError(f"Invalid {table} field(s): {bad}")


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
    return {
        "id": account_id,
        "org_name": org_name,
        "plan": "trial",
        "status": "active",
        "created_at": now,
    }


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
    """Update account fields (H3: column allowlist enforced)."""
    _validate_fields(kwargs, _ACCOUNT_FIELDS, "accounts")
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
    return {
        "id": user_id,
        "account_id": account_id,
        "email": email,
        "created_at": now,
        "role": "owner",
    }


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
    """Update user fields (H3: column allowlist enforced)."""
    _validate_fields(kwargs, _USER_FIELDS, "users")
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    db.execute(f"UPDATE users SET {sets} WHERE id = ?", vals)
    db.commit()
    return db.total_changes > 0


def delete_user_and_account(user_id: str, account_id: str) -> bool:
    """Delete user, account, and all related data (AC-7)."""
    db = get_db()
    # Purge invitations and memberships for the entire account
    db.execute("DELETE FROM invitations WHERE account_id = ?", (account_id,))
    db.execute("DELETE FROM memberships WHERE account_id = ?", (account_id,))
    # Purge all users of this account (email_tokens + sessions + users)
    user_ids = [
        r[0] for r in db.execute("SELECT id FROM users WHERE account_id = ?", (account_id,)).fetchall()
    ]
    for uid in user_ids:
        db.execute("DELETE FROM email_tokens WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM users WHERE account_id = ?", (account_id,))
    db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_SESSION_DURATION_DAYS = 7


def create_session(
    user_id: str, user_agent: str = "", ip_address: str = ""
) -> str:
    """Create a new session. Returns the session token (opaque, 128-bit hex)."""
    db = get_db()
    session_id = secrets.token_hex(16)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=_SESSION_DURATION_DAYS)
    db.execute(
        "INSERT INTO sessions (id, user_id, created_at, expires_at, revoked, user_agent, ip_address) VALUES (?, ?, ?, ?, 0, ?, ?)",
        (session_id, user_id, now.isoformat(), expires.isoformat(), user_agent[:256], ip_address[:64]),
    )
    db.commit()
    return session_id


def validate_session(session_id: str) -> dict[str, Any] | None:
    """Validate a session token. Returns user + account info if valid, None otherwise."""
    db = get_db()
    row = db.execute(
        """SELECT s.*, u.email, u.account_id, u.role, u.email_verified_at,
                  a.org_name, a.plan, a.status AS account_status
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


# ---------------------------------------------------------------------------
# Session management — extended (A.2)
# ---------------------------------------------------------------------------


def list_user_sessions(user_id: str) -> list[dict[str, Any]]:
    """List active (non-revoked, non-expired) sessions for a user."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        """SELECT id, created_at, expires_at, user_agent, ip_address
           FROM sessions
           WHERE user_id = ? AND revoked = 0 AND expires_at > ?
           ORDER BY created_at DESC""",
        (user_id, now),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_all_sessions_except(user_id: str, keep_session_id: str) -> int:
    """Revoke all sessions for a user except the specified one (AC-6)."""
    db = get_db()
    db.execute(
        "UPDATE sessions SET revoked = 1 WHERE user_id = ? AND id != ? AND revoked = 0",
        (user_id, keep_session_id),
    )
    db.commit()
    return db.total_changes


def revoke_specific_session(session_id: str, user_id: str) -> bool:
    """Revoke a specific session (must belong to user)."""
    db = get_db()
    db.execute(
        "UPDATE sessions SET revoked = 1 WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    db.commit()
    return db.total_changes > 0


# ---------------------------------------------------------------------------
# Membership CRUD (A.3)
# ---------------------------------------------------------------------------

_INVITATION_EXPIRY_HOURS = 72


def create_membership(account_id: str, user_id: str, role: str) -> dict[str, Any]:
    """Create a membership. Returns the membership dict."""
    db = get_db()
    mid = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO memberships (id, account_id, user_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (mid, account_id, user_id, role, now),
    )
    db.commit()
    return {"id": mid, "account_id": account_id, "user_id": user_id, "role": role, "created_at": now}


def get_membership(account_id: str, user_id: str) -> dict[str, Any] | None:
    """Get a membership by account + user."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM memberships WHERE account_id = ? AND user_id = ?",
        (account_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_memberships(account_id: str) -> list[dict[str, Any]]:
    """List all memberships for an account, enriched with user info."""
    db = get_db()
    rows = db.execute(
        """SELECT m.id, m.account_id, m.user_id, m.role, m.created_at,
                  u.email, u.display_name, u.email_verified_at
           FROM memberships m
           JOIN users u ON m.user_id = u.id
           WHERE m.account_id = ?
           ORDER BY m.created_at ASC""",
        (account_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_membership_role(account_id: str, user_id: str, new_role: str) -> bool:
    """Update a membership role."""
    db = get_db()
    db.execute(
        "UPDATE memberships SET role = ? WHERE account_id = ? AND user_id = ?",
        (new_role, account_id, user_id),
    )
    db.commit()
    return db.total_changes > 0


def delete_membership(account_id: str, user_id: str) -> bool:
    """Delete a membership."""
    db = get_db()
    db.execute(
        "DELETE FROM memberships WHERE account_id = ? AND user_id = ?",
        (account_id, user_id),
    )
    db.commit()
    return db.total_changes > 0


def count_owners(account_id: str) -> int:
    """Count owner memberships for an account (AC-3: last owner guard)."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) FROM memberships WHERE account_id = ? AND role = 'owner'",
        (account_id,),
    ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Invitation CRUD (A.3)
# ---------------------------------------------------------------------------


def create_invitation(
    account_id: str, email: str, role: str, invited_by: str
) -> tuple[str, str]:
    """Create an invitation. Returns (invitation_id, raw_token)."""
    db = get_db()
    inv_id = str(uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=_INVITATION_EXPIRY_HOURS)
    db.execute(
        """INSERT INTO invitations (id, account_id, email, role, token_hash, invited_by, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (inv_id, account_id, email.lower(), role, token_hash, invited_by, now.isoformat(), expires.isoformat()),
    )
    db.commit()
    return inv_id, raw_token


def get_invitation_by_id(invitation_id: str, account_id: str) -> dict[str, Any] | None:
    """Get an invitation by ID (scoped to account)."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM invitations WHERE id = ? AND account_id = ?",
        (invitation_id, account_id),
    ).fetchone()
    return dict(row) if row else None


def get_invitation_by_token(raw_token: str) -> dict[str, Any] | None:
    """Get an invitation by raw token. Returns None if not found, expired, revoked, or used."""
    db = get_db()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = db.execute(
        """SELECT inv.*, a.org_name
           FROM invitations inv
           JOIN accounts a ON inv.account_id = a.id
           WHERE inv.token_hash = ? AND inv.revoked = 0 AND inv.accepted_at IS NULL""",
        (token_hash,),
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


def list_invitations(account_id: str) -> list[dict[str, Any]]:
    """List pending (non-revoked, non-accepted, non-expired) invitations for an account."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        """SELECT id, email, role, invited_by, created_at, expires_at
           FROM invitations
           WHERE account_id = ? AND revoked = 0 AND accepted_at IS NULL AND expires_at > ?
           ORDER BY created_at DESC""",
        (account_id, now),
    ).fetchall()
    return [dict(r) for r in rows]


def accept_invitation(invitation_id: str) -> bool:
    """Mark an invitation as accepted."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE invitations SET accepted_at = ? WHERE id = ? AND accepted_at IS NULL",
        (now, invitation_id),
    )
    db.commit()
    return db.total_changes > 0


def revoke_invitation(invitation_id: str, account_id: str) -> bool:
    """Revoke a pending invitation."""
    db = get_db()
    db.execute(
        "UPDATE invitations SET revoked = 1 WHERE id = ? AND account_id = ? AND accepted_at IS NULL",
        (invitation_id, account_id),
    )
    db.commit()
    return db.total_changes > 0


def refresh_invitation_token(invitation_id: str, account_id: str) -> str | None:
    """Regenerate token + reset expiry for a pending invitation. Returns new raw token."""
    db = get_db()
    row = db.execute(
        "SELECT id FROM invitations WHERE id = ? AND account_id = ? AND revoked = 0 AND accepted_at IS NULL",
        (invitation_id, account_id),
    ).fetchone()
    if not row:
        return None
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    new_expires = (datetime.now(timezone.utc) + timedelta(hours=_INVITATION_EXPIRY_HOURS)).isoformat()
    db.execute(
        "UPDATE invitations SET token_hash = ?, expires_at = ? WHERE id = ?",
        (token_hash, new_expires, invitation_id),
    )
    db.commit()
    return raw_token
