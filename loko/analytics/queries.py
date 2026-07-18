"""LOKO Analytics — Read-only query functions for the dashboard API.

All functions are fail-open: if analytics.db is missing or unreadable,
they return empty results (never raise).  Each function opens its own
read connection to avoid contention with the background writer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _get_read_connection() -> sqlite3.Connection | None:
    """Open a read-only connection to analytics.db.

    Returns None if the DB file does not exist (fail-open).
    """
    from loko.analytics.db import _resolve_db_path

    db_path = _resolve_db_path()
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _default_date_range() -> tuple[str, str]:
    """Return (from_date, to_date) defaulting to last 30 days."""
    today = date.today()
    return (today - timedelta(days=30)).isoformat(), (today + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# KPI overview
# ---------------------------------------------------------------------------


def query_kpi_overview(
    bot_id: str, from_date: str, to_date: str
) -> dict[str, Any]:
    """High-level KPI metrics for a bot in [from_date, to_date)."""
    conn = _get_read_connection()
    if conn is None:
        return _empty_kpi()
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN event_type = 'session_start'
                      THEN session_id END) AS sessions,
                COUNT(CASE WHEN event_type = 'message_in' THEN 1 END) AS messages,
                COUNT(CASE WHEN event_type = 'escalade' THEN 1 END) AS escalations,
                COUNT(CASE WHEN event_type IN ('feedback_up', 'feedback_down')
                      THEN 1 END) AS feedbacks,
                COUNT(CASE WHEN event_type = 'feedback_up' THEN 1 END) AS feedback_up,
                COUNT(CASE WHEN event_type = 'feedback_down'
                      THEN 1 END) AS feedback_down,
                COUNT(CASE WHEN event_type = 'error' THEN 1 END) AS errors,
                COUNT(CASE WHEN event_type = 'garde_fou_inapproprie'
                      THEN 1 END) AS guardrail_blocks
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
            """,
            (bot_id, from_date, to_date),
        ).fetchone()

        sessions = row["sessions"]
        messages = row["messages"]
        feedbacks = row["feedbacks"]

        return {
            "sessions": sessions,
            "messages": messages,
            "escalations": row["escalations"],
            "escalation_rate": row["escalations"] / sessions if sessions else 0.0,
            "feedbacks": feedbacks,
            "feedback_up": row["feedback_up"],
            "feedback_down": row["feedback_down"],
            "feedback_rate": row["feedback_up"] / feedbacks if feedbacks else 0.0,
            "errors": row["errors"],
            "error_rate": row["errors"] / messages if messages else 0.0,
            "guardrail_blocks": row["guardrail_blocks"],
        }
    except Exception:
        logger.warning("query_kpi_overview failed (fail-open)", exc_info=True)
        return _empty_kpi()
    finally:
        conn.close()


def _empty_kpi() -> dict[str, Any]:
    return {
        "sessions": 0,
        "messages": 0,
        "escalations": 0,
        "escalation_rate": 0.0,
        "feedbacks": 0,
        "feedback_up": 0,
        "feedback_down": 0,
        "feedback_rate": 0.0,
        "errors": 0,
        "error_rate": 0.0,
        "guardrail_blocks": 0,
    }


# ---------------------------------------------------------------------------
# Intent distribution
# ---------------------------------------------------------------------------


def query_intent_distribution(
    bot_id: str, from_date: str, to_date: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Top intents by volume with average confidence scores."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        # Aggregate from raw events (includes scores)
        rows = conn.execute(
            """
            SELECT
                intent_id,
                COUNT(*) AS total,
                AVG(score_top1) AS avg_score_top1,
                AVG(score_margin) AS avg_score_margin
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
              AND event_type = 'classification'
              AND intent_id IS NOT NULL
            GROUP BY intent_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (bot_id, from_date, to_date, limit),
        ).fetchall()

        return [
            {
                "intent_id": r["intent_id"],
                "count": r["total"],
                "avg_score_top1": round(r["avg_score_top1"], 4) if r["avg_score_top1"] is not None else None,
                "avg_score_margin": round(r["avg_score_margin"], 4) if r["avg_score_margin"] is not None else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("query_intent_distribution failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Latency trends
# ---------------------------------------------------------------------------


def query_latency_trends(
    bot_id: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    """Daily p50/p95 latency from raw events."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                DATE(ts) AS day,
                latency_ms
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
              AND latency_ms IS NOT NULL
            ORDER BY day, latency_ms
            """,
            (bot_id, from_date, to_date),
        ).fetchall()

        if not rows:
            return []

        from itertools import groupby

        result = []
        for day, group in groupby(rows, key=lambda r: r["day"]):
            latencies = [r["latency_ms"] for r in group]
            n = len(latencies)
            p50 = latencies[int(n * 0.5)] if n > 0 else None
            p95 = latencies[int(min(n * 0.95, n - 1))] if n > 0 else None
            result.append({
                "day": day,
                "p50_latency_ms": p50,
                "p95_latency_ms": p95,
                "event_count": n,
            })
        return result
    except Exception:
        logger.warning("query_latency_trends failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Event type breakdown
# ---------------------------------------------------------------------------


def query_event_type_breakdown(
    bot_id: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    """Distribution of event types over the period."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT event_type, COUNT(*) AS total
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
            GROUP BY event_type
            ORDER BY total DESC
            """,
            (bot_id, from_date, to_date),
        ).fetchall()

        return [{"event_type": r["event_type"], "count": r["total"]} for r in rows]
    except Exception:
        logger.warning("query_event_type_breakdown failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Event type timeseries
# ---------------------------------------------------------------------------


def query_event_type_timeseries(
    bot_id: str,
    from_date: str,
    to_date: str,
    event_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Daily breakdown of event types (for line charts)."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            query = f"""
                SELECT DATE(ts) AS day, event_type, COUNT(*) AS total
                FROM events
                WHERE bot_id = ? AND ts >= ? AND ts < ?
                  AND event_type IN ({placeholders})
                GROUP BY day, event_type
                ORDER BY day, event_type
            """
            params: tuple = (bot_id, from_date, to_date, *event_types)
        else:
            query = """
                SELECT DATE(ts) AS day, event_type, COUNT(*) AS total
                FROM events
                WHERE bot_id = ? AND ts >= ? AND ts < ?
                GROUP BY day, event_type
                ORDER BY day, event_type
            """
            params = (bot_id, from_date, to_date)

        rows = conn.execute(query, params).fetchall()
        return [
            {"day": r["day"], "event_type": r["event_type"], "count": r["total"]}
            for r in rows
        ]
    except Exception:
        logger.warning("query_event_type_timeseries failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Escalation analysis
# ---------------------------------------------------------------------------


def query_escalation_analysis(
    bot_id: str, from_date: str, to_date: str
) -> dict[str, Any]:
    """Escalation reasons breakdown from meta JSON field."""
    conn = _get_read_connection()
    if conn is None:
        return {"total_escalations": 0, "by_motif": [], "by_intent": []}
    try:
        rows = conn.execute(
            """
            SELECT intent_id, meta
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
              AND event_type = 'escalade'
            """,
            (bot_id, from_date, to_date),
        ).fetchall()

        motif_counts: dict[str, int] = {}
        intent_motif: dict[tuple[str, str], int] = {}

        for r in rows:
            meta = json.loads(r["meta"]) if r["meta"] else {}
            motif = meta.get("motif", "unknown")
            intent = r["intent_id"] or "unknown"
            motif_counts[motif] = motif_counts.get(motif, 0) + 1
            key = (intent, motif)
            intent_motif[key] = intent_motif.get(key, 0) + 1

        return {
            "total_escalations": len(rows),
            "by_motif": sorted(
                [{"motif": m, "count": c} for m, c in motif_counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            ),
            "by_intent": sorted(
                [{"intent_id": k[0], "motif": k[1], "count": c} for k, c in intent_motif.items()],
                key=lambda x: x["count"],
                reverse=True,
            ),
        }
    except Exception:
        logger.warning("query_escalation_analysis failed (fail-open)", exc_info=True)
        return {"total_escalations": 0, "by_motif": [], "by_intent": []}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Guardrail triggers
# ---------------------------------------------------------------------------


def query_guardrail_triggers(
    bot_id: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    """Which guardrail rules fire most."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT meta
            FROM events
            WHERE bot_id = ? AND ts >= ? AND ts < ?
              AND event_type = 'garde_fou_inapproprie'
            """,
            (bot_id, from_date, to_date),
        ).fetchall()

        rule_counts: dict[tuple[str, str], int] = {}
        for r in rows:
            meta = json.loads(r["meta"]) if r["meta"] else {}
            rule_id = meta.get("rule_id", "unknown")
            category = meta.get("category", "")
            key = (rule_id, category)
            rule_counts[key] = rule_counts.get(key, 0) + 1

        return sorted(
            [
                {"rule_id": k[0], "category": k[1] or None, "count": c}
                for k, c in rule_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )
    except Exception:
        logger.warning("query_guardrail_triggers failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------


def query_session_events(
    bot_id: str, session_id: str
) -> list[dict[str, Any]]:
    """All analytics events for a specific session (for debugging)."""
    conn = _get_read_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                event_id, ts, event_type, turn, intent_id, sub_motif_id,
                decision, score_top1, score_margin, latency_ms,
                error_code, channel, meta
            FROM events
            WHERE bot_id = ? AND session_id = ?
            ORDER BY ts
            """,
            (bot_id, session_id),
        ).fetchall()

        return [
            {
                "event_id": r["event_id"],
                "ts": r["ts"],
                "event_type": r["event_type"],
                "turn": r["turn"],
                "intent_id": r["intent_id"],
                "sub_motif_id": r["sub_motif_id"],
                "decision": r["decision"],
                "score_top1": r["score_top1"],
                "score_margin": r["score_margin"],
                "latency_ms": r["latency_ms"],
                "error_code": r["error_code"],
                "channel": r["channel"],
                "meta": json.loads(r["meta"]) if r["meta"] else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("query_session_events failed (fail-open)", exc_info=True)
        return []
    finally:
        conn.close()
