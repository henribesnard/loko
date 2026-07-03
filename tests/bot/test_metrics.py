"""Tests for the metrics aggregation module."""

import json
import sqlite3
from pathlib import Path

import pytest

from loko.bot.metrics import (
    BotMetrics,
    compute_metrics,
    get_misclassified_turns,
    get_session_replay,
)
from loko.bot.session_store import SessionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "sessions.db"


@pytest.fixture
def store(db_path: Path) -> SessionStore:
    return SessionStore(db_path)


@pytest.fixture
def populated_db(db_path: Path, store: SessionStore) -> Path:
    """Create a database with diverse session data for metrics testing."""
    conn = sqlite3.connect(str(db_path))

    # Insert sessions with various states and intents
    sessions = [
        ("s1", "bot1", "fin", "2024-01-01T10:00:00", "2024-01-01T10:05:00", 1, 0, 0, "facturation", None),
        ("s2", "bot1", "fin", "2024-01-01T11:00:00", "2024-01-01T11:03:00", 1, 0, 0, "facturation", None),
        ("s3", "bot1", "escalade", "2024-01-01T12:00:00", "2024-01-01T12:02:00", 1, 0, 0, "facturation", None),
        ("s4", "bot1", "fin", "2024-01-01T13:00:00", "2024-01-01T13:04:00", 1, 0, 0, "livraison", None),
        ("s5", "bot1", "escalade", "2024-01-01T14:00:00", "2024-01-01T14:01:00", 1, 0, 0, "livraison", None),
        ("s6", "bot1", "timeout", "2024-01-01T15:00:00", "2024-01-01T15:10:00", 0, 0, 0, None, None),
    ]
    for s in sessions:
        conn.execute(
            """INSERT INTO sessions
               (session_id, bot_id, state, created_at, last_activity_at,
                demandes_count, clarifications_count, reformulation_count,
                current_intent, current_sub_motif)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            s,
        )

    # Insert turns (including some with clarification templates)
    turns = [
        ("t1", "s1", "bot", "Bienvenue", "2024-01-01T10:00:00", "presentation", None, None, None, None, None),
        ("t2", "s1", "user", "Ma facture est fausse", "2024-01-01T10:00:30", None, None, None, "facturation", None, None),
        ("t3", "s1", "bot", "Voici les informations", "2024-01-01T10:01:00", None, None, None, None, None, None),
        ("t4", "s3", "bot", "Clarification", "2024-01-01T12:00:30", "clarification_inter", '["facturation", "livraison"]', None, None, None, None),
        ("t5", "s5", "user", "Je veux parler à quelqu'un", "2024-01-01T14:00:30", None, None, None, "livraison", None, None),
    ]
    for t in turns:
        conn.execute(
            """INSERT INTO turns
               (turn_id, session_id, role, content, timestamp,
                template_key, buttons, button_selected,
                intent, sub_motif, sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            t,
        )

    # Insert traces with latencies
    traces = [
        ("t2", "s1", "classification_l1", json.dumps({"scores": [("facturation", 0.85)]}), 25.3),
        ("t2", "s1", "retrieval", json.dumps({"chunks": 3}), 45.1),
        ("t2", "s1", "generation", json.dumps({}), 180.5),
        ("t5", "s5", "classification_l1", json.dumps({"scores": [("livraison", 0.42)]}), 22.0),
    ]
    for tr in traces:
        conn.execute(
            "INSERT INTO traces (turn_id, session_id, step, detail, latency_ms) VALUES (?, ?, ?, ?, ?)",
            tr,
        )

    # Insert feedback
    feedback = [
        ("s1", "t3", "positive", "", "2024-01-01T10:02:00"),
        ("s3", "t4", "negative", "Pas la bonne intention", "2024-01-01T12:01:00"),
        ("s5", "t5", "negative", "Trop lent", "2024-01-01T14:01:00"),
    ]
    for f in feedback:
        conn.execute(
            "INSERT INTO feedback (session_id, turn_id, rating, comment, timestamp) VALUES (?, ?, ?, ?, ?)",
            f,
        )

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Tests: compute_metrics
# ---------------------------------------------------------------------------

class TestComputeMetrics:
    def test_empty_db(self, db_path: Path, store: SessionStore):
        metrics = compute_metrics(db_path)
        assert metrics.total_sessions == 0
        assert metrics.selfcare_rate == 0.0

    def test_nonexistent_db(self, tmp_path: Path):
        metrics = compute_metrics(tmp_path / "nope.db")
        assert metrics.total_sessions == 0

    def test_session_counts(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        assert metrics.total_sessions == 6
        assert metrics.completed_sessions == 3  # fin
        assert metrics.escalated_sessions == 2  # escalade
        assert metrics.timed_out_sessions == 1  # timeout

    def test_selfcare_rate(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        # 4 non-escalated / 6 total = 0.6667
        assert 0.66 < metrics.selfcare_rate < 0.67

    def test_escalation_rate(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        # 2 escalated / 6 total = 0.3333
        assert 0.33 < metrics.escalation_rate < 0.34

    def test_clarification_rate(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        # 1 session with clarification (s3) / 6 total
        assert metrics.clarification_rate > 0

    def test_selfcare_by_intent(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        # facturation: 2 fin + 1 escalade = 2/3 selfcare
        assert "facturation" in metrics.selfcare_by_intent
        assert 0.66 < metrics.selfcare_by_intent["facturation"] < 0.67

        # livraison: 1 fin + 1 escalade = 1/2 selfcare
        assert "livraison" in metrics.selfcare_by_intent
        assert metrics.selfcare_by_intent["livraison"] == 0.5

    def test_escalation_by_intent(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        assert metrics.escalation_by_intent.get("facturation") == 1
        assert metrics.escalation_by_intent.get("livraison") == 1

    def test_latency(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        assert metrics.latency_p50_ms > 0
        assert metrics.latency_p95_ms >= metrics.latency_p50_ms

    def test_feedback_counts(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        assert metrics.feedback_positive == 1
        assert metrics.feedback_negative == 2
        assert 0.33 < metrics.feedback_rate < 0.34

    def test_recent_sessions(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        assert len(metrics.recent_sessions) == 6
        # Most recent first
        assert metrics.recent_sessions[0]["session_id"] == "s6"

    def test_to_dict(self, populated_db: Path):
        metrics = compute_metrics(populated_db)
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert "total_sessions" in d
        assert "selfcare_by_intent" in d


# ---------------------------------------------------------------------------
# Tests: get_misclassified_turns
# ---------------------------------------------------------------------------

class TestGetMisclassifiedTurns:
    def test_returns_negative_feedback_turns(self, populated_db: Path):
        turns = get_misclassified_turns(populated_db)
        assert len(turns) == 2  # 2 negative feedbacks

    def test_includes_user_message(self, populated_db: Path):
        turns = get_misclassified_turns(populated_db)
        messages = {t["user_message"] for t in turns}
        # t4 is a bot turn with negative feedback, t5 is a user turn
        assert any("parler" in m for m in messages)

    def test_includes_classification_scores(self, populated_db: Path):
        turns = get_misclassified_turns(populated_db)
        # At least one turn should have scores from the trace
        has_scores = any(len(t["classification_scores"]) > 0 for t in turns)
        assert has_scores

    def test_empty_db(self, db_path: Path, store: SessionStore):
        turns = get_misclassified_turns(db_path)
        assert turns == []


# ---------------------------------------------------------------------------
# Tests: get_session_replay
# ---------------------------------------------------------------------------

class TestGetSessionReplay:
    def test_returns_full_replay(self, populated_db: Path):
        replay = get_session_replay(populated_db, "s1")
        assert replay is not None
        assert replay["session"]["session_id"] == "s1"
        assert len(replay["turns"]) >= 2
        assert len(replay["traces"]) >= 2
        assert len(replay["feedback"]) == 1

    def test_returns_none_for_unknown_session(self, populated_db: Path):
        replay = get_session_replay(populated_db, "nonexistent")
        assert replay is None

    def test_traces_have_parsed_detail(self, populated_db: Path):
        replay = get_session_replay(populated_db, "s1")
        assert replay is not None
        for trace in replay["traces"]:
            assert isinstance(trace["detail"], dict)
