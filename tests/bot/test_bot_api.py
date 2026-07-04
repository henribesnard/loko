"""Tests for the bot admin and public API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from loko.api.api_keys import generate_api_key
from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test FastAPI app with temp data dir."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RAGKIT_ENV", "test")
    # Set admin token for test admin access
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token-12345")

    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()

    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Headers with admin token."""
    return {"Authorization": "Bearer test-admin-token-12345"}


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
        status="published",
    )
    save_bot_config(config)

    # C7: register a mock orchestrator — mocks centralized in loko.testing.mocks
    from loko.api.bot_public import register_orchestrator
    from loko.bot.generation import BotGenerator
    from loko.bot.orchestrator import BotOrchestrator
    from loko.bot.retrieval_filter import FilteredRetriever
    from loko.testing.mocks import (
        InMemorySearchBackend,
        MockEscalationProvider,
        MockLLMProvider,
        _MockClassifier,
    )

    register_orchestrator(
        config.bot_id,
        BotOrchestrator(
            classifier=_MockClassifier(),
            retriever=FilteredRetriever(InMemorySearchBackend()),
            generator=BotGenerator(MockLLMProvider(response="[Mock] test")),
            escalation=MockEscalationProvider(),
        ),
    )

    return config


@pytest.fixture
def api_key(sample_config, tmp_path, monkeypatch) -> str:
    """Generate an API key for the sample bot."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    raw_key, _ = generate_api_key(
        sample_config.bot_id,
        label="test-key",
        allowed_origins=["*"],
    )
    return raw_key


@pytest.fixture
def auth_headers(api_key):
    """Headers with bot API key."""
    return {"Authorization": f"Bearer {api_key}"}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

class TestAdminAPI:
    def test_create_bot(self, client, admin_headers):
        res = client.post("/api/bot/", json={"name": "NewBot"}, headers=admin_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "NewBot"
        assert "bot_id" in data

    def test_create_bot_no_auth(self, client):
        """P0-2: Admin endpoints require token."""
        res = client.post("/api/bot/", json={"name": "NewBot"})
        assert res.status_code == 401

    def test_list_bots(self, client, sample_config, admin_headers):
        res = client.get("/api/bot/", headers=admin_headers)
        assert res.status_code == 200
        bots = res.json()
        assert len(bots) >= 1

    def test_get_bot(self, client, sample_config, admin_headers):
        res = client.get(f"/api/bot/{sample_config.bot_id}", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["name"] == "TestBot"

    def test_get_nonexistent_bot(self, client, admin_headers):
        res = client.get("/api/bot/nonexistent", headers=admin_headers)
        assert res.status_code == 404

    def test_update_bot(self, client, sample_config, admin_headers):
        res = client.put(
            f"/api/bot/{sample_config.bot_id}",
            json={"name": "UpdatedBot"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["name"] == "UpdatedBot"

    def test_delete_bot(self, client, sample_config, admin_headers):
        res = client.delete(
            f"/api/bot/{sample_config.bot_id}", headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        res2 = client.get(
            f"/api/bot/{sample_config.bot_id}", headers=admin_headers,
        )
        assert res2.status_code == 404


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_create_session(self, client, sample_config, auth_headers):
        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert "session_id" in data
        assert data["state"] == "attente_demande"
        assert len(data.get("events", [])) > 0

    def test_create_session_no_auth(self, client, sample_config):
        """P0-1: Public endpoints require API key."""
        res = client.post(f"/api/v1/bot/{sample_config.bot_id}/sessions")
        assert res.status_code == 401

    def test_create_session_wrong_key(self, client, sample_config):
        """P0-1: Wrong API key returns 401."""
        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers={"Authorization": "Bearer loko_invalid_key"},
        )
        assert res.status_code == 401

    def test_create_session_nonexistent_bot(self, client, api_key):
        res = client.post(
            "/api/v1/bot/nonexistent/sessions",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        # 401 because key is scoped to different bot
        assert res.status_code == 401

    def test_get_session(self, client, sample_config, auth_headers):
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        res = client.get(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["session_id"] == session_id

    def test_get_nonexistent_session(self, client, sample_config, auth_headers):
        res = client.get(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/nonexistent",
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_send_message_sse(self, client, sample_config, auth_headers):
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "bonjour", "type": "text"},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            content = response.read().decode()
            assert "event:" in content
            assert "data:" in content

    def test_feedback(self, client, sample_config, auth_headers):
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "positive", "comment": "good"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "recorded"

    def test_message_too_long(self, client, sample_config, auth_headers):
        """P0-5: Message text limited to 2000 chars."""
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "x" * 10000, "type": "text"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_invalid_rating(self, client, sample_config, auth_headers):
        """P2-7: Rating must be 'positive' or 'negative'."""
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "neutral"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_traces_not_public(self, client, sample_config, auth_headers):
        """P1-2: Traces endpoint removed from public API."""
        create_res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = create_res.json()["session_id"]

        res = client.get(
            f"/api/v1/bot/{sample_config.bot_id}/sessions/{session_id}/traces",
            headers=auth_headers,
        )
        # Should be 404 or 405 since the route no longer exists
        assert res.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Path traversal (P0-4)
# ---------------------------------------------------------------------------

class TestPathTraversal:
    def test_bot_id_with_dots_rejected(self, client, api_key):
        """P0-4: bot_id with dots/traversal patterns rejected at storage level."""
        from loko.bot.session_store import get_bot_dir
        with pytest.raises(ValueError):
            get_bot_dir("..")
        with pytest.raises(ValueError):
            get_bot_dir("..%2f..%2fetc")

    def test_bot_id_with_slash_is_404(self, client, admin_headers):
        """P0-4: bot_id with slash is handled as different path."""
        res = client.get(
            "/api/bot/test%2F..%2Fetc",
            headers=admin_headers,
        )
        # URL-encoded slash may cause 404 or 422
        assert res.status_code in (404, 422, 400)


# ---------------------------------------------------------------------------
# Origin check (P1-4)
# ---------------------------------------------------------------------------

class TestOriginCheck:
    def test_origin_restricted(self, client, sample_config, tmp_path, monkeypatch):
        """P0-1: Key with restricted origins rejects other origins."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        raw_key, _ = generate_api_key(
            sample_config.bot_id,
            label="restricted",
            allowed_origins=["https://allowed.com"],
        )

        # Request from disallowed origin
        res = client.post(
            f"/api/v1/bot/{sample_config.bot_id}/sessions",
            headers={
                "Authorization": f"Bearer {raw_key}",
                "Origin": "https://evil.com",
            },
        )
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Security headers (P0-3)
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_security_headers_on_health(self, client):
        """P0-3: Security headers present on responses."""
        res = client.get("/health")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
