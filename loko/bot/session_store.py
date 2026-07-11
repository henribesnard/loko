"""LOKO Bot — Session persistence (SQLite).

Stores bot sessions, turns, traces, and feedback in a per-bot SQLite
database at ~/.loko/bots/{bot_id}/sessions.db.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loko.bot.models import BotSession, BotState, TraceEvent, Turn

logger = logging.getLogger(__name__)


class SessionStore:
    """SQLite-backed session store for a single bot."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Sessions CRUD
    # ------------------------------------------------------------------

    def create_session(self, session: BotSession) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (session_id, bot_id, state, created_at, last_activity_at,
                    demandes_count, clarifications_count, reformulation_count,
                    current_intent, current_sub_motif, pending_candidates,
                    original_query)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.session_id,
                    session.bot_id,
                    session.state.value,
                    session.created_at,
                    session.last_activity_at,
                    session.demandes_count,
                    session.clarifications_count_current_demande,
                    session.reformulation_count_current_demande,
                    session.current_intent,
                    session.current_sub_motif,
                    json.dumps(session.pending_candidates),
                    session.original_query,
                ),
            )

    def get_session(self, session_id: str) -> BotSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None

            # Load turns
            turn_rows = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()

            turns = [_row_to_turn(r) for r in turn_rows]

            return BotSession(
                session_id=row["session_id"],
                bot_id=row["bot_id"],
                state=BotState(row["state"]),
                created_at=row["created_at"],
                last_activity_at=row["last_activity_at"],
                demandes_count=row["demandes_count"],
                clarifications_count_current_demande=row["clarifications_count"],
                reformulation_count_current_demande=row["reformulation_count"],
                current_intent=row["current_intent"],
                current_sub_motif=row["current_sub_motif"],
                pending_candidates=json.loads(row["pending_candidates"] or "[]"),
                original_query=row["original_query"],
                transcript=turns,
            )

    def update_session(self, session: BotSession) -> None:
        """Persist the full session state (upsert)."""
        self.create_session(session)

    def list_sessions(
        self,
        bot_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT session_id, state, created_at, last_activity_at,
                          demandes_count, current_intent
                   FROM sessions WHERE bot_id = ?
                   ORDER BY last_activity_at DESC LIMIT ? OFFSET ?""",
                (bot_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def purge_expired(self, bot_id: str, before: str) -> int:
        """Delete sessions with last_activity_at before the given ISO timestamp."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE bot_id = ? AND last_activity_at < ?",
                (bot_id, before),
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    def add_turn(self, session_id: str, turn: Turn) -> None:
        # PRO-1: mask PII at persistence (never in-flight)
        from loko.bot.pii import mask_pii

        content = mask_pii(turn.content) if turn.role == "user" else turn.content

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO turns
                   (turn_id, session_id, role, content, timestamp,
                    template_key, buttons, button_selected,
                    intent, sub_motif, sources)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn.turn_id,
                    session_id,
                    turn.role,
                    content,
                    turn.timestamp,
                    turn.template_key.value if turn.template_key else None,
                    json.dumps(turn.buttons) if turn.buttons else None,
                    turn.button_selected,
                    turn.intent,
                    turn.sub_motif,
                    json.dumps(turn.sources) if turn.sources else None,
                ),
            )

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def add_trace(self, session_id: str, trace: TraceEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO traces
                   (turn_id, session_id, step, detail, latency_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    trace.turn_id,
                    session_id,
                    trace.step,
                    json.dumps(trace.detail),
                    trace.latency_ms,
                ),
            )

    def get_traces(self, session_id: str) -> list[TraceEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM traces WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
            return [
                TraceEvent(
                    turn_id=r["turn_id"],
                    step=r["step"],
                    detail=json.loads(r["detail"] or "{}"),
                    latency_ms=r["latency_ms"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def add_feedback(
        self,
        session_id: str,
        turn_id: str,
        rating: str,
        comment: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO feedback
                   (session_id, turn_id, rating, comment, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session_id,
                    turn_id,
                    rating,
                    comment,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_feedback(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM feedback WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    demandes_count INTEGER NOT NULL DEFAULT 0,
    clarifications_count INTEGER NOT NULL DEFAULT 0,
    reformulation_count INTEGER NOT NULL DEFAULT 0,
    current_intent TEXT,
    current_sub_motif TEXT,
    pending_candidates TEXT,
    original_query TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_bot
    ON sessions(bot_id, last_activity_at);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    template_key TEXT,
    buttons TEXT,
    button_selected TEXT,
    intent TEXT,
    sub_motif TEXT,
    sources TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_session
    ON turns(session_id, timestamp);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    detail TEXT,
    latency_ms REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_traces_session
    ON traces(session_id);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    rating TEXT NOT NULL,
    comment TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_session
    ON feedback(session_id);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_turn(row: sqlite3.Row) -> Turn:
    buttons = json.loads(row["buttons"]) if row["buttons"] else None
    sources = json.loads(row["sources"]) if row["sources"] else None
    tk = row["template_key"]
    from loko.bot.models import TemplateKey

    template_key = TemplateKey(tk) if tk else None

    return Turn(
        turn_id=row["turn_id"],
        role=row["role"],
        content=row["content"],
        timestamp=row["timestamp"],
        template_key=template_key,
        buttons=buttons,
        button_selected=row["button_selected"],
        intent=row["intent"],
        sub_motif=row["sub_motif"],
        sources=sources,
    )


# ---------------------------------------------------------------------------
# Bot config store (simple JSON file)
# ---------------------------------------------------------------------------


def get_bots_dir() -> Path:
    """Return the root directory for bot data (~/.loko/bots/)."""
    import os

    custom = os.environ.get("LOKO_DATA_DIR")
    root = Path(custom) if custom else Path.home() / ".loko"
    bots_dir = root / "bots"
    bots_dir.mkdir(parents=True, exist_ok=True)
    return bots_dir


def get_bot_dir(bot_id: str, *, create: bool = True) -> Path:
    """Return the directory for a specific bot.

    Args:
        bot_id: Bot identifier (must be a valid slug).
        create: If True (default), create the directory if missing.
                Set to False for read-only lookups to avoid disk
                pollution by enumeration.

    Raises:
        ValueError: If bot_id fails slug validation or results in
                    a path outside the bots directory (traversal).
    """
    from loko.bot.models import validate_slug

    validate_slug(bot_id, "bot_id")

    bots_dir = get_bots_dir()
    bot_dir = (bots_dir / bot_id).resolve()

    # Path traversal guard
    if bots_dir.resolve() not in bot_dir.parents and bot_dir != bots_dir.resolve():
        raise ValueError(f"Invalid bot_id: path traversal detected — {bot_id!r}")

    if create:
        bot_dir.mkdir(parents=True, exist_ok=True)
    return bot_dir


def get_session_store(bot_id: str) -> SessionStore:
    """Get or create a SessionStore for a bot."""
    db_path = get_bot_dir(bot_id) / "sessions.db"
    return SessionStore(db_path)
