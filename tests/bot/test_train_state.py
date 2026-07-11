"""Tests for L4 — Training job state persistence.

Covers:
  - State persisted to disk on training start
  - State persisted on training completion/failure
  - After restart: 'running' requalified as 'failed/interrupted'
  - GET /train/status reads persisted state after in-memory state cleared
  - New training possible after recovery
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent
from loko.bot.session_store import get_bot_dir


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ENV", "test")
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token-12345")

    from loko.api.bot_admin import _TRAINING_STATE

    _TRAINING_STATE.clear()

    from loko.api.bot_public import clear_orchestrators

    clear_orchestrators()

    from loko.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer test-admin-token-12345"}


@pytest.fixture
def sample_bot(tmp_path, monkeypatch) -> BotConfig:
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    config = BotConfig(
        name="TrainStateBot",
        intents=[
            Intent(
                id="livraison",
                label="Livraison",
                definition="Livraison",
                examples=[f"ex {i}" for i in range(10)],
            ),
            Intent(
                id="hors_perimetre",
                label="HP",
                definition="HP",
                examples=["hp"],
                is_system=True,
            ),
            Intent(
                id="demande_conseiller",
                label="DC",
                definition="DC",
                examples=["dc"],
                is_system=True,
            ),
        ],
    )
    save_bot_config(config)
    return config


class TestTrainStatePersistence:
    """L4: training state persisted to disk and recovered on boot."""

    def test_persist_and_load_state(self, tmp_path, monkeypatch, sample_bot):
        """State is written to and read from train_state.json."""
        from loko.api.bot_admin import (
            _TRAINING_STATE,
            _load_train_state,
            _persist_train_state,
        )

        bot_id = sample_bot.bot_id
        _TRAINING_STATE[bot_id] = {
            "status": "running",
            "step": "l1_training",
            "result": None,
        }
        _persist_train_state(bot_id)

        state_path = get_bot_dir(bot_id) / "train_state.json"
        assert state_path.exists()

        loaded = _load_train_state(bot_id)
        assert loaded is not None
        assert loaded["status"] == "running"
        assert loaded["step"] == "l1_training"

    def test_recover_interrupted_job(self, tmp_path, monkeypatch, sample_bot):
        """A 'running' state on disk is requalified as 'failed/interrupted'."""
        from loko.api.bot_admin import (
            _TRAINING_STATE,
            _load_train_state,
            recover_interrupted_jobs,
        )

        bot_id = sample_bot.bot_id

        # Simulate a running state left on disk (process died)
        state_path = get_bot_dir(bot_id) / "train_state.json"
        state_path.write_text(
            json.dumps({"status": "running", "step": "l1_training"}),
            encoding="utf-8",
        )

        # Clear in-memory state (simulates restart)
        _TRAINING_STATE.clear()

        recover_interrupted_jobs()

        # Check disk state
        recovered = _load_train_state(bot_id)
        assert recovered["status"] == "failed"
        assert recovered["error"] == "interrupted"

        # Check in-memory state
        assert _TRAINING_STATE[bot_id]["status"] == "failed"
        assert _TRAINING_STATE[bot_id]["error"] == "interrupted"

    def test_completed_not_requalified(self, tmp_path, monkeypatch, sample_bot):
        """A 'completed' state on disk is NOT changed by recovery."""
        from loko.api.bot_admin import (
            _TRAINING_STATE,
            _load_train_state,
            recover_interrupted_jobs,
        )

        bot_id = sample_bot.bot_id

        state_path = get_bot_dir(bot_id) / "train_state.json"
        state_path.write_text(
            json.dumps({"status": "completed", "step": "done"}),
            encoding="utf-8",
        )
        _TRAINING_STATE.clear()

        recover_interrupted_jobs()

        loaded = _load_train_state(bot_id)
        assert loaded["status"] == "completed"
        assert bot_id not in _TRAINING_STATE

    def test_status_endpoint_reads_disk(self, client, admin_headers, sample_bot):
        """GET /train/status falls back to disk state when in-memory is empty."""
        from loko.api.bot_admin import _TRAINING_STATE

        bot_id = sample_bot.bot_id

        # Write a failed state to disk
        state_path = get_bot_dir(bot_id) / "train_state.json"
        state_path.write_text(
            json.dumps(
                {"status": "failed", "error": "interrupted", "step": "interrupted"}
            ),
            encoding="utf-8",
        )
        _TRAINING_STATE.clear()

        res = client.get(f"/api/bot/{bot_id}/train/status", headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["error"] == "interrupted"

    def test_idle_when_no_state(self, client, admin_headers, sample_bot):
        """GET /train/status returns idle when no state exists at all."""
        from loko.api.bot_admin import _TRAINING_STATE

        _TRAINING_STATE.clear()

        bot_id = sample_bot.bot_id
        res = client.get(f"/api/bot/{bot_id}/train/status", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "idle"
