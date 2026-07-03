"""Tests for the bot admin and public API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test FastAPI app with temp data dir."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()

    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def sample_config(tmp_path, monkeypatch) -> BotConfig:
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    config = BotConfig(
        name="TestBot",
        intents=[
            Intent(id="livraison", label="Livraison", definition="Livraison",
                   examples=[f"ex {i}" for i in range(10)]),
            Intent(id="hors_perimetre", label="HP", definition="HP",
                   examples=["hp"], is_system=True),
            Intent(id="demande_conseiller", label="DC", definition="DC",
                   examples=["dc"], is_system=True),
        ],
    )
    save_bot_config(config)
    return config


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

class TestAdminAPI:
    def test_create_bot(self, client):
        res = client.post("/api/bot/", json={"name": "NewBot"})
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "NewBot"
        assert "bot_id" in data

    def test_list_bots(self, client, sample_config):
        res = client.get("/api/bot/")
        assert res.status_code == 200
        bots = res.json()
        assert len(bots) >= 1

    def test_get_bot(self, client, sample_config):
        res = client.get(f"/api/bot/{sample_config.bot_id}")
        assert res.status_code == 200
        assert res.json()["name"] == "TestBot"

    def test_get_nonexistent_bot(self, client):
        res = client.get("/api/bot/nonexistent")
        assert res.status_code == 404

    def test_update_bot(self, client, sample_config):
        res = client.put(
            f"/api/bot/{sample_config.bot_id}",
            json={"name": "UpdatedBot"},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "UpdatedBot"

    def test_delete_bot(self, client, sample_config):
        res = client.delete(f"/api/bot/{sample_config.bot_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        res2 = client.get(f"/api/bot/{sample_config.bot_id}")
        assert res2.status_code == 404


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_create_session(self, client, sample_config):
        res = client.post(f"/api/v1/bot/{sample_config.bot_id}/sessions")
        assert res.status_code == 201
        data = res.json()
        assert "session_id" in data
        assert data["state"] == "attente_demande"
        assert len(data.get("events", [])) > 0

    def test_create_session_nonexistent_bot(self, client):
        res = client.post("/api/v1/bot/nonexistent/sessions")
        assert res.status_code == 404

    def test_get_session(self, client, sample_config):
        create_res = client.post(f"/api/v1/bot/{sample_config.bot_id}/sessions")
        session_id = create_res.json()["session_id"]

        res = client.get(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}"
        )
        assert res.status_code == 200
        assert res.json()["session_id"] == session_id

    def test_get_nonexistent_session(self, client, sample_config):
        res = client.get(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/nonexistent"
        )
        assert res.status_code == 404

    def test_send_message_sse(self, client, sample_config):
        create_res = client.post(f"/api/v1/bot/{sample_config.bot_id}/sessions")
        session_id = create_res.json()["session_id"]

        # Send a message and get SSE response
        with client.stream(
            "POST",
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "bonjour", "type": "text"},
        ) as response:
            assert response.status_code == 200
            content = response.read().decode()
            assert "event:" in content
            assert "data:" in content

    def test_feedback(self, client, sample_config):
        create_res = client.post(f"/api/v1/bot/{sample_config.bot_id}/sessions")
        session_id = create_res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "positive", "comment": "good"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "recorded"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
