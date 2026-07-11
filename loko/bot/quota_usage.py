"""LOKO Bot — API key quota usage tracking (Lot PRO-6 §7.6).

Monthly counters per API key: sessions, messages, LLM tokens.
Calendar reset at UTC month boundary.

Completes the rate limiting (P0-5, per minute) with monthly budgets.
Test keys (PRO-3) are excluded from counting.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QuotaConfig(BaseModel):
    """Per-key monthly quota limits."""
    sessions_mois: int = Field(default=0, ge=0, description="0 = unlimited")
    messages_mois: int = Field(default=0, ge=0, description="0 = unlimited")
    tokens_llm_mois: int = Field(default=0, ge=0, description="0 = unlimited")


class QuotaStatus(BaseModel):
    """Current quota usage status."""
    key_id: str
    month: str  # YYYY-MM
    sessions_used: int = 0
    messages_used: int = 0
    tokens_used: int = 0
    sessions_limit: int = 0
    messages_limit: int = 0
    tokens_limit: int = 0
    warning: bool = False  # True if any metric >= 80%
    exceeded: bool = False  # True if any metric >= limit


# Warning threshold (80%)
_WARNING_RATIO = 0.80


def _current_month() -> str:
    """Current UTC month as YYYY-MM."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _next_month_reset() -> str:
    """ISO timestamp of the first second of next month (UTC)."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        reset = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        reset = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return reset.isoformat()


class QuotaUsageStore:
    """SQLite-backed monthly quota counter store."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quota_counters (
                    key_id TEXT NOT NULL,
                    month TEXT NOT NULL,
                    sessions_count INTEGER DEFAULT 0,
                    messages_count INTEGER DEFAULT 0,
                    tokens_count INTEGER DEFAULT 0,
                    PRIMARY KEY (key_id, month)
                )
            """)

    def increment(
        self,
        key_id: str,
        metric: Literal["sessions", "messages", "tokens"],
        amount: int = 1,
    ) -> int:
        """Increment a counter for the current month.

        Returns the new total for the metric.
        """
        month = _current_month()
        column = f"{metric}_count"

        with sqlite3.connect(self._db_path) as conn:
            # Upsert
            conn.execute(
                f"INSERT INTO quota_counters (key_id, month, {column}) "
                f"VALUES (?, ?, ?) "
                f"ON CONFLICT(key_id, month) DO UPDATE SET {column} = {column} + ?",
                (key_id, month, amount, amount),
            )

            row = conn.execute(
                f"SELECT {column} FROM quota_counters "
                f"WHERE key_id = ? AND month = ?",
                (key_id, month),
            ).fetchone()

        return row[0] if row else amount

    def get_usage(self, key_id: str, month: str | None = None) -> dict[str, int]:
        """Get current usage counters for a key."""
        month = month or _current_month()

        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT sessions_count, messages_count, tokens_count "
                "FROM quota_counters WHERE key_id = ? AND month = ?",
                (key_id, month),
            ).fetchone()

        if not row:
            return {"sessions": 0, "messages": 0, "tokens": 0}

        return {
            "sessions": row[0],
            "messages": row[1],
            "tokens": row[2],
        }

    def check_quota(
        self,
        key_id: str,
        config: QuotaConfig,
        metric: Literal["sessions", "messages", "tokens"],
    ) -> QuotaStatus:
        """Check if a key has exceeded its quota for a given metric.

        Returns QuotaStatus with exceeded=True if over limit.
        """
        usage = self.get_usage(key_id)
        month = _current_month()

        limits = {
            "sessions": config.sessions_mois,
            "messages": config.messages_mois,
            "tokens": config.tokens_llm_mois,
        }

        exceeded = False
        warning = False

        for m, limit in limits.items():
            if limit <= 0:
                continue  # unlimited
            current = usage.get(m, 0)
            if current >= limit:
                exceeded = True
            elif current >= limit * _WARNING_RATIO:
                warning = True

        return QuotaStatus(
            key_id=key_id,
            month=month,
            sessions_used=usage.get("sessions", 0),
            messages_used=usage.get("messages", 0),
            tokens_used=usage.get("tokens", 0),
            sessions_limit=config.sessions_mois,
            messages_limit=config.messages_mois,
            tokens_limit=config.tokens_llm_mois,
            warning=warning,
            exceeded=exceeded,
        )

    def is_exceeded(
        self,
        key_id: str,
        config: QuotaConfig,
        metric: Literal["sessions", "messages", "tokens"],
    ) -> bool:
        """Quick check if a specific metric is exceeded."""
        limit = {
            "sessions": config.sessions_mois,
            "messages": config.messages_mois,
            "tokens": config.tokens_llm_mois,
        }.get(metric, 0)

        if limit <= 0:
            return False  # unlimited

        usage = self.get_usage(key_id)
        return usage.get(metric, 0) >= limit

    def cleanup_old_months(self, keep_months: int = 3) -> int:
        """Remove counters older than keep_months."""
        now = datetime.now(timezone.utc)
        # Calculate cutoff month
        cutoff_year = now.year
        cutoff_month = now.month - keep_months
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff = f"{cutoff_year:04d}-{cutoff_month:02d}"

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM quota_counters WHERE month < ?",
                (cutoff,),
            )
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: QuotaUsageStore | None = None


def get_quota_usage_store() -> QuotaUsageStore:
    """Get the global quota usage store instance."""
    global _store
    if _store is None:
        db_dir = Path(os.environ.get("LOKO_DATA_DIR", "data"))
        db_dir.mkdir(parents=True, exist_ok=True)
        _store = QuotaUsageStore(db_dir / "loko_quota_usage.db")
    return _store


# ---------------------------------------------------------------------------
# Helpers for runtime integration
# ---------------------------------------------------------------------------

def get_quota_reset_header() -> str:
    """Return the X-Quota-Reset header value (ISO datetime)."""
    return _next_month_reset()
