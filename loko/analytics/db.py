"""LOKO Analytics — Database access layer.

Manages the analytics.db SQLite database (WAL mode, append-only).
Located alongside loko_accounts.db in LOKO_DATA_DIR.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from loko.analytics.schema import create_schema

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get("LOKO_DATA_DIR", "data"))
_DB_PATH: Path | None = None
_connection: sqlite3.Connection | None = None


def _resolve_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path(os.environ.get("LOKO_DATA_DIR", "data")) / "analytics.db"
    return _DB_PATH


def get_analytics_db() -> sqlite3.Connection:
    """Return a module-level singleton connection to analytics.db (WAL mode)."""
    global _connection
    if _connection is None:
        db_path = _resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(db_path), check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")
        create_schema(_connection)
        _connection.commit()
        logger.info("Analytics DB initialized at %s", db_path)
    return _connection


def close_analytics_db() -> None:
    """Close the singleton connection (for clean shutdown)."""
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None


def insert_events_batch(events: list[dict[str, Any]]) -> int:
    """Insert a batch of event dicts into the events table.

    Returns the number of rows inserted.
    Uses a fresh connection to avoid blocking the singleton
    during long batch writes.
    """
    if not events:
        return 0

    # Ensure schema exists (idempotent — the singleton does this on first call)
    get_analytics_db()

    db_path = _resolve_db_path()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executemany(
            """
            INSERT OR IGNORE INTO events
            (event_id, ts, account_id, bot_id, session_id, turn,
             event_type, intent_id, sub_motif_id, decision,
             score_top1, score_margin, latency_ms, error_code,
             channel, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    e["event_id"],
                    e["ts"],
                    e["account_id"],
                    e["bot_id"],
                    e["session_id"],
                    e.get("turn"),
                    e["event_type"],
                    e.get("intent_id"),
                    e.get("sub_motif_id"),
                    e.get("decision"),
                    e.get("score_top1"),
                    e.get("score_margin"),
                    e.get("latency_ms"),
                    e.get("error_code"),
                    e.get("channel"),
                    json.dumps(e["meta"], ensure_ascii=False) if e.get("meta") else None,
                )
                for e in events
            ],
        )
        conn.commit()
        return len(events)
    finally:
        conn.close()


def purge_events(before_iso: str) -> int:
    """Delete raw events older than the given ISO timestamp.

    Returns the number of deleted rows.
    """
    db_path = _resolve_db_path()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        cursor = conn.execute("DELETE FROM events WHERE ts < ?", (before_iso,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def compute_daily_rollups(day_iso: str) -> int:
    """Compute aggregated rollups for a given day (YYYY-MM-DD).

    Inserts or replaces rows in daily_rollups.
    Returns the number of rollup rows upserted.
    """
    db_path = _resolve_db_path()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        # Delete existing rollups for this day (idempotent re-computation)
        conn.execute("DELETE FROM daily_rollups WHERE day = ?", (day_iso,))

        cursor = conn.execute(
            """
            INSERT INTO daily_rollups
                (day, bot_id, intent_id, sub_motif_id, decision, event_type,
                 count, p50_latency, p95_latency)
            SELECT
                ? AS day,
                bot_id,
                COALESCE(intent_id, '') AS intent_id,
                COALESCE(sub_motif_id, '') AS sub_motif_id,
                COALESCE(decision, '') AS decision,
                event_type,
                COUNT(*) AS count,
                NULL AS p50_latency,
                NULL AS p95_latency
            FROM events
            WHERE ts >= ? AND ts < date(?, '+1 day')
            GROUP BY bot_id, intent_id, sub_motif_id, decision, event_type
            """,
            (day_iso, day_iso, day_iso),
        )
        upserted = cursor.rowcount

        # Compute latency percentiles for event types that have latency_ms
        # SQLite doesn't have native percentile functions, so we do it in Python
        _compute_latency_percentiles(conn, day_iso)

        conn.commit()
        return upserted
    finally:
        conn.close()


def _compute_latency_percentiles(conn: sqlite3.Connection, day_iso: str) -> None:
    """Update p50 and p95 latency in daily_rollups from raw events."""
    rows = conn.execute(
        """
        SELECT bot_id,
               COALESCE(intent_id, '') AS intent_id,
               COALESCE(sub_motif_id, '') AS sub_motif_id,
               COALESCE(decision, '') AS decision,
               event_type,
               latency_ms
        FROM events
        WHERE ts >= ? AND ts < date(?, '+1 day')
          AND latency_ms IS NOT NULL
        ORDER BY bot_id, intent_id, sub_motif_id, decision, event_type, latency_ms
        """,
        (day_iso, day_iso),
    ).fetchall()

    if not rows:
        return

    from itertools import groupby

    def key_fn(row: tuple) -> tuple:
        return row[:5]  # bot_id, intent_id, sub_motif_id, decision, event_type

    for key, group in groupby(rows, key=key_fn):
        latencies = [r[5] for r in group if r[5] is not None]
        if not latencies:
            continue
        latencies.sort()
        n = len(latencies)
        p50 = latencies[int(n * 0.5)] if n > 0 else None
        p95 = latencies[int(min(n * 0.95, n - 1))] if n > 0 else None

        conn.execute(
            """
            UPDATE daily_rollups
            SET p50_latency = ?, p95_latency = ?
            WHERE day = ? AND bot_id = ? AND intent_id = ?
              AND sub_motif_id = ? AND decision = ? AND event_type = ?
            """,
            (p50, p95, day_iso, *key),
        )
