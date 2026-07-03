"""Tests for the dashboard API endpoints."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent
from loko.bot.session_store import get_bot_dir, _SCHEMA_SQL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()
    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def bot_with_sessions(tmp_path, monkeypatch) -> str:
    """Create a bot with sessions in a temp directory."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    bot_id = "test-dash-bot"

    # Create bot config
    config = BotConfig(
        bot_id=bot_id,
        name="Dashboard Test Bot",
        intents=[
            Intent(
                id="facturation",
                label="Facturation",
                definition="Questions de facturation",
                examples=[f"exemple facturation {i}" for i in range(10)],
            ),
            Intent(
                id="hors_perimetre",
                label="Hors périmètre",
                definition="Hors périmètre",
                examples=[],
                is_system=True,
            ),
        ],
    )
    save_bot_config(config)

    # Create sessions DB
    bot_dir = get_bot_dir(bot_id)
    db_path = bot_dir / "sessions.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_SQL)

    # Insert session data
    conn.execute(
        """INSERT INTO sessions
           (session_id, bot_id, state, created_at, last_activity_at,
            demandes_count, clarifications_count, reformulation_count,
            current_intent, current_sub_motif)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("s1", bot_id, "fin", "2024-01-01T10:00:00", "2024-01-01T10:05:00",
         1, 0, 0, "facturation", None),
    )
    conn.execute(
        """INSERT INTO turns
           (turn_id, session_id, role, content, timestamp,
            template_key, buttons, button_selected,
            intent, sub_motif, sources)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("t1", "s1", "user", "Ma facture", "2024-01-01T10:00:30",
         None, None, None, "facturation", None, None),
    )
    conn.execute(
        "INSERT INTO feedback (session_id, turn_id, rating, comment, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("s1", "t1", "negative", "Mauvaise réponse", "2024-01-01T10:01:00"),
    )
    conn.commit()
    conn.close()

    return bot_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDashboardMetrics:
    def test_get_metrics_empty_bot(self, client: TestClient):
        resp = client.get("/api/bot/nonexistent/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 0

    def test_get_metrics_with_sessions(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 1
        assert data["completed_sessions"] == 1


class TestDashboardSessions:
    def test_list_recent_sessions(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "s1"

    def test_replay_session(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/sessions/s1/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["session_id"] == "s1"
        assert len(data["turns"]) >= 1
        assert len(data["feedback"]) == 1

    def test_replay_unknown_session(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/sessions/unknown/replay")
        assert resp.status_code == 404


class TestDashboardMisclassified:
    def test_list_misclassified(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/misclassified")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_message"] == "Ma facture"


class TestDashboardAddExample:
    def test_add_training_example(self, client: TestClient, bot_with_sessions: str):
        resp = client.post(
            f"/api/bot/{bot_with_sessions}/dashboard/add-example",
            json={"intent_id": "facturation", "text": "ma facture est incorrecte"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "added"
        assert data["examples_count"] == 11

    def test_add_duplicate_example(self, client: TestClient, bot_with_sessions: str):
        resp = client.post(
            f"/api/bot/{bot_with_sessions}/dashboard/add-example",
            json={"intent_id": "facturation", "text": "exemple facturation 0"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"

    def test_add_example_unknown_intent(self, client: TestClient, bot_with_sessions: str):
        resp = client.post(
            f"/api/bot/{bot_with_sessions}/dashboard/add-example",
            json={"intent_id": "nonexistent", "text": "test"},
        )
        assert resp.status_code == 404


class TestDashboardSuggestions:
    def test_get_suggestions(self, client: TestClient, bot_with_sessions: str):
        resp = client.get(f"/api/bot/{bot_with_sessions}/dashboard/suggestions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_suggestions_unknown_bot(self, client: TestClient):
        resp = client.get("/api/bot/unknown/dashboard/suggestions")
        assert resp.status_code == 404
