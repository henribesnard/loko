"""LOKO Assistant — Monthly call quota per account.

Simple SQLite counter following the same pattern as
``loko.bot.quota_usage.QuotaUsageStore``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from loko.db.accounts import get_account

logger = logging.getLogger(__name__)

ASSISTANT_DEFAULT_QUOTA = 50  # calls per month (trial plan)
_UNLIMITED_PLANS = frozenset({"standard", "enterprise", "internal"})


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _get_db_path() -> str:
    db_dir = Path(os.environ.get("LOKO_DATA_DIR", "data"))
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "loko_quota_usage.db")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assistant_usage (
            account_id TEXT NOT NULL,
            month TEXT NOT NULL,
            call_count INTEGER DEFAULT 0,
            PRIMARY KEY (account_id, month)
        )
    """)


def _get_limit(account_id: str) -> int:
    """Return the monthly assistant call limit for an account. 0 = unlimited."""
    if not account_id:
        return 0  # Ops/internal — unlimited

    account = get_account(account_id)
    if not account:
        return ASSISTANT_DEFAULT_QUOTA

    plan = account.get("plan", "trial")
    if plan in _UNLIMITED_PLANS:
        return 0  # unlimited
    return ASSISTANT_DEFAULT_QUOTA


def get_assistant_usage(account_id: str) -> int:
    """Return current month call count for account."""
    month = _current_month()
    db_path = _get_db_path()
    with sqlite3.connect(db_path) as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT call_count FROM assistant_usage WHERE account_id = ? AND month = ?",
            (account_id, month),
        ).fetchone()
        return row[0] if row else 0


def check_assistant_quota(account_id: str) -> None:
    """Raise 429 if the account has exceeded its monthly assistant quota."""
    limit = _get_limit(account_id)
    if limit == 0:
        return  # unlimited

    usage = get_assistant_usage(account_id)
    if usage >= limit:
        raise HTTPException(
            429,
            f"Quota assistant atteint : {limit} appels/mois. "
            f"Passez au forfait Standard pour un usage illimité.",
        )


def increment_assistant_usage(account_id: str) -> None:
    """Increment the monthly assistant call counter."""
    if not account_id:
        return

    month = _current_month()
    db_path = _get_db_path()
    with sqlite3.connect(db_path) as conn:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT INTO assistant_usage (account_id, month, call_count)
            VALUES (?, ?, 1)
            ON CONFLICT(account_id, month)
            DO UPDATE SET call_count = call_count + 1
            """,
            (account_id, month),
        )
