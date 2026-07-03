"""LOKO Bot — Metrics aggregation from session store.

Computes dashboard metrics by querying the SQLite session database:
  - Selfcare rate (per intent)
  - Escalation rate (per motif)
  - Clarification rate
  - Latency P50 / P95
  - Feedback positive/negative breakdown
  - Recent sessions summary
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BotMetrics:
    """Aggregated bot metrics."""
    total_sessions: int = 0
    completed_sessions: int = 0
    escalated_sessions: int = 0
    timed_out_sessions: int = 0

    selfcare_rate: float = 0.0  # sessions terminées sans escalade / total
    escalation_rate: float = 0.0
    clarification_rate: float = 0.0  # sessions ayant eu au moins 1 clarification

    # Per-intent breakdown
    selfcare_by_intent: dict[str, float] = None  # type: ignore[assignment]
    escalation_by_intent: dict[str, int] = None  # type: ignore[assignment]

    # Latency
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0

    # Feedback
    feedback_positive: int = 0
    feedback_negative: int = 0
    feedback_rate: float = 0.0  # positive / total feedback

    # Recent sessions
    recent_sessions: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.selfcare_by_intent is None:
            self.selfcare_by_intent = {}
        if self.escalation_by_intent is None:
            self.escalation_by_intent = {}
        if self.recent_sessions is None:
            self.recent_sessions = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "completed_sessions": self.completed_sessions,
            "escalated_sessions": self.escalated_sessions,
            "timed_out_sessions": self.timed_out_sessions,
            "selfcare_rate": round(self.selfcare_rate, 4),
            "escalation_rate": round(self.escalation_rate, 4),
            "clarification_rate": round(self.clarification_rate, 4),
            "selfcare_by_intent": self.selfcare_by_intent,
            "escalation_by_intent": self.escalation_by_intent,
            "latency_p50_ms": round(self.latency_p50_ms, 1),
            "latency_p95_ms": round(self.latency_p95_ms, 1),
            "feedback_positive": self.feedback_positive,
            "feedback_negative": self.feedback_negative,
            "feedback_rate": round(self.feedback_rate, 4),
            "recent_sessions": self.recent_sessions,
        }


def compute_metrics(db_path: Path, limit_recent: int = 20) -> BotMetrics:
    """Compute aggregated metrics from a bot's session database.

    Args:
        db_path: Path to the SQLite sessions.db file.
        limit_recent: Number of recent sessions to include.

    Returns:
        BotMetrics with all computed values.
    """
    if not db_path.exists():
        return BotMetrics()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        metrics = BotMetrics()

        # --- Session counts by state ---
        rows = conn.execute(
            "SELECT state, COUNT(*) as cnt FROM sessions GROUP BY state"
        ).fetchall()

        state_counts: dict[str, int] = {}
        for r in rows:
            state_counts[r["state"]] = r["cnt"]

        metrics.total_sessions = sum(state_counts.values())
        metrics.completed_sessions = state_counts.get("fin", 0)
        metrics.escalated_sessions = state_counts.get("escalade", 0)
        metrics.timed_out_sessions = state_counts.get("timeout", 0)

        if metrics.total_sessions > 0:
            non_escalated = metrics.total_sessions - metrics.escalated_sessions
            metrics.selfcare_rate = non_escalated / metrics.total_sessions
            metrics.escalation_rate = metrics.escalated_sessions / metrics.total_sessions

        # --- Clarification rate ---
        clarif_count = conn.execute(
            "SELECT COUNT(DISTINCT session_id) as cnt FROM turns WHERE template_key IN ('clarification_inter', 'clarification_intra')"
        ).fetchone()
        if clarif_count and metrics.total_sessions > 0:
            metrics.clarification_rate = clarif_count["cnt"] / metrics.total_sessions

        # --- Selfcare by intent ---
        intent_rows = conn.execute("""
            SELECT current_intent, state, COUNT(*) as cnt
            FROM sessions
            WHERE current_intent IS NOT NULL
            GROUP BY current_intent, state
        """).fetchall()

        intent_total: dict[str, int] = {}
        intent_selfcare: dict[str, int] = {}
        for r in intent_rows:
            intent = r["current_intent"]
            cnt = r["cnt"]
            intent_total[intent] = intent_total.get(intent, 0) + cnt
            if r["state"] != "escalade":
                intent_selfcare[intent] = intent_selfcare.get(intent, 0) + cnt

        for intent, total in intent_total.items():
            sc = intent_selfcare.get(intent, 0)
            metrics.selfcare_by_intent[intent] = round(sc / total, 4) if total > 0 else 0.0

        # --- Escalation by intent ---
        esc_rows = conn.execute("""
            SELECT current_intent, COUNT(*) as cnt
            FROM sessions
            WHERE state = 'escalade' AND current_intent IS NOT NULL
            GROUP BY current_intent
        """).fetchall()
        for r in esc_rows:
            metrics.escalation_by_intent[r["current_intent"]] = r["cnt"]

        # --- Latency P50/P95 from traces ---
        latencies = conn.execute(
            "SELECT latency_ms FROM traces WHERE latency_ms > 0 ORDER BY latency_ms"
        ).fetchall()

        if latencies:
            vals = [r["latency_ms"] for r in latencies]
            n = len(vals)
            metrics.latency_p50_ms = vals[n // 2]
            metrics.latency_p95_ms = vals[int(n * 0.95)]

        # --- Feedback ---
        fb_rows = conn.execute(
            "SELECT rating, COUNT(*) as cnt FROM feedback GROUP BY rating"
        ).fetchall()
        for r in fb_rows:
            if r["rating"] == "positive":
                metrics.feedback_positive = r["cnt"]
            elif r["rating"] == "negative":
                metrics.feedback_negative = r["cnt"]

        total_fb = metrics.feedback_positive + metrics.feedback_negative
        if total_fb > 0:
            metrics.feedback_rate = metrics.feedback_positive / total_fb

        # --- Recent sessions ---
        recent_rows = conn.execute("""
            SELECT session_id, state, created_at, last_activity_at,
                   demandes_count, current_intent
            FROM sessions
            ORDER BY last_activity_at DESC
            LIMIT ?
        """, (limit_recent,)).fetchall()
        metrics.recent_sessions = [dict(r) for r in recent_rows]

        return metrics

    finally:
        conn.close()


def get_misclassified_turns(
    db_path: Path,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get turns with negative feedback — candidates for re-training.

    Returns turns where the user gave negative feedback, along with
    the classification trace data (intent, scores).
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT
                f.session_id,
                f.turn_id,
                f.rating,
                f.comment,
                f.timestamp as feedback_time,
                t.content as user_message,
                t.intent,
                t.sub_motif,
                s.current_intent as session_intent
            FROM feedback f
            JOIN turns t ON f.turn_id = t.turn_id
            JOIN sessions s ON f.session_id = s.session_id
            WHERE f.rating = 'negative'
            ORDER BY f.timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()

        results = []
        for r in rows:
            # Try to find classification trace for context
            trace_row = conn.execute("""
                SELECT detail FROM traces
                WHERE session_id = ? AND step = 'classification_l1'
                ORDER BY rowid DESC LIMIT 1
            """, (r["session_id"],)).fetchone()

            classification_detail = {}
            if trace_row and trace_row["detail"]:
                classification_detail = json.loads(trace_row["detail"])

            results.append({
                "session_id": r["session_id"],
                "turn_id": r["turn_id"],
                "user_message": r["user_message"],
                "classified_intent": r["intent"] or r["session_intent"],
                "sub_motif": r["sub_motif"],
                "feedback_comment": r["comment"],
                "feedback_time": r["feedback_time"],
                "classification_scores": classification_detail.get("scores", []),
            })

        return results

    finally:
        conn.close()


def get_session_replay(db_path: Path, session_id: str) -> dict[str, Any] | None:
    """Get full session replay data (transcript + traces + feedback).

    Used for the dashboard conversation replay feature.
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        session = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not session:
            return None

        turns = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()

        traces = conn.execute(
            "SELECT * FROM traces WHERE session_id = ? ORDER BY rowid",
            (session_id,),
        ).fetchall()

        feedback = conn.execute(
            "SELECT * FROM feedback WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()

        return {
            "session": dict(session),
            "turns": [
                {
                    **dict(t),
                    "buttons": json.loads(t["buttons"]) if t["buttons"] else None,
                    "sources": json.loads(t["sources"]) if t["sources"] else None,
                }
                for t in turns
            ],
            "traces": [
                {
                    **dict(t),
                    "detail": json.loads(t["detail"]) if t["detail"] else {},
                }
                for t in traces
            ],
            "feedback": [dict(f) for f in feedback],
        }

    finally:
        conn.close()
