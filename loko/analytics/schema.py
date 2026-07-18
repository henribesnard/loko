"""LOKO Analytics — Database schema (v1).

Defines the events table (append-only journal) and daily_rollups
(aggregated metrics for long-term dashboard queries).

The analytics database is a **separate SQLite file** (analytics.db),
never on the critical path of bot responses.
"""

from __future__ import annotations

import sqlite3

ANALYTICS_SCHEMA_VERSION = 1

# Closed taxonomy of event types (v1).
# Adding a new type requires a schema version bump.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session_start",
        "message_in",
        "classification",
        "clarification_inter",
        "clarification_intra",
        "answer_served",
        "sources_cited",
        "enquete_shown",
        "enquete_answered",
        "feedback_up",
        "feedback_down",
        "escalade",
        "hors_perimetre",
        "garde_fou_inapproprie",
        "timeout",
        "cloture_douce",
        "fin_ferme",
        "session_end",
        "error",
        "quota_hit",
        "events_dropped",
    }
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create analytics tables and indexes if they do not exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id    TEXT PRIMARY KEY,
            ts          TEXT NOT NULL,
            account_id  TEXT NOT NULL,
            bot_id      TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            turn        INTEGER,
            event_type  TEXT NOT NULL,
            intent_id   TEXT,
            sub_motif_id TEXT,
            decision    TEXT,
            score_top1  REAL,
            score_margin REAL,
            latency_ms  INTEGER,
            error_code  TEXT,
            channel     TEXT,
            meta        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_account_ts
            ON events(account_id, ts);
        CREATE INDEX IF NOT EXISTS idx_events_bot_ts
            ON events(bot_id, ts);
        CREATE INDEX IF NOT EXISTS idx_events_session
            ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_type_ts
            ON events(event_type, ts);

        CREATE TABLE IF NOT EXISTS daily_rollups (
            day         TEXT NOT NULL,
            bot_id      TEXT NOT NULL,
            intent_id   TEXT NOT NULL DEFAULT '',
            sub_motif_id TEXT NOT NULL DEFAULT '',
            decision    TEXT NOT NULL DEFAULT '',
            event_type  TEXT NOT NULL,
            count       INTEGER NOT NULL DEFAULT 0,
            p50_latency REAL,
            p95_latency REAL,
            PRIMARY KEY (day, bot_id, intent_id, sub_motif_id, decision, event_type)
        );

        CREATE INDEX IF NOT EXISTS idx_rollups_bot_day
            ON daily_rollups(bot_id, day);
        """
    )
