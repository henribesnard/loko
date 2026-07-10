"""K1: Tests for publish endpoint 422 error codes (model integrity)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ENV", "test")
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token")
    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()
    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer test-admin-token"}


def _make_bot(tmp_path, monkeypatch) -> BotConfig:
    """Create a bot with valid intents (8+ examples each)."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    config = BotConfig(
        name="TestPub",
        intents=[
            Intent(id="livraison", label="Livraison", definition="D",
                   examples=[f"livraison ex {i}" for i in range(10)]),
            Intent(id="facturation", label="Facturation", definition="D",
                   examples=[f"facturation ex {i}" for i in range(10)]),
            Intent(id="hors_perimetre", label="HP", definition="HP",
                   examples=["hp"], is_system=True),
            Intent(id="demande_conseiller", label="DC", definition="DC",
                   examples=["dc"], is_system=True),
        ],
    )
    save_bot_config(config)
    return config


class TestPublish422Codes:
    """K1: Model integrity errors return 422 with machine codes."""

    def test_manifest_missing(self, client, admin_headers, tmp_path, monkeypatch):
        """No manifest → 422 manifest_missing."""
        config = _make_bot(tmp_path, monkeypatch)
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "model_integrity"
        assert body["code"] == "manifest_missing"
        assert body["bot_id"] == config.bot_id

    def test_manifest_invalid_json(self, client, admin_headers, tmp_path, monkeypatch):
        """Corrupt manifest (invalid JSON) → 422 manifest_invalid."""
        config = _make_bot(tmp_path, monkeypatch)
        # Create manifest file with corrupt content
        from loko.bot.classifier.manifest import get_manifest_path
        manifest_path = get_manifest_path(config.bot_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("NOT VALID JSON {{{{")
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "model_integrity"
        assert body["code"] == "manifest_invalid"

    def test_hash_mismatch(self, client, admin_headers, tmp_path, monkeypatch):
        """Model file modified after manifest → 422 hash_mismatch."""
        config = _make_bot(tmp_path, monkeypatch)
        from loko.bot.classifier.model_store import get_model_dir
        from loko.bot.classifier.manifest import get_manifest_path
        model_dir = get_model_dir(config.bot_id, "level1")
        model_dir.mkdir(parents=True, exist_ok=True)
        # Write a fake model file
        (model_dir / "model.safetensors").write_bytes(b"real model content")
        (model_dir / "config.json").write_text('{"architectures": ["test"]}')
        # Write manifest with wrong hashes (uses "schema" and "levels" keys)
        manifest = {
            "schema": 1,
            "levels": {
                "level1": {
                    "files": {"model.safetensors": "0000dead", "config.json": "0000beef"},
                    "labels": ["livraison", "facturation"],
                    "n_train_examples": 20,
                },
            },
            "dataset_hash": "abc123",
            "created_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = get_manifest_path(config.bot_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "model_integrity"
        assert body["code"] == "hash_mismatch"

    def test_retrain_required(self, client, admin_headers, tmp_path, monkeypatch):
        """Examples changed since training → 422 retrain_required."""
        config = _make_bot(tmp_path, monkeypatch)
        from loko.bot.classifier.model_store import get_model_dir
        from loko.bot.classifier.manifest import compute_file_hashes, get_manifest_path
        model_dir = get_model_dir(config.bot_id, "level1")
        model_dir.mkdir(parents=True, exist_ok=True)
        # Write model files
        (model_dir / "model.safetensors").write_bytes(b"model data")
        (model_dir / "config.json").write_text('{"architectures": ["test"]}')
        # Compute real hashes for these files
        real_hashes = compute_file_hashes(model_dir)
        # Write manifest with correct hashes but WRONG dataset_hash
        manifest = {
            "schema": 1,
            "levels": {
                "level1": {
                    "files": real_hashes,
                    "labels": ["livraison", "facturation", "hors_perimetre", "demande_conseiller"],
                    "n_train_examples": 20,
                },
            },
            "dataset_hash": "old_hash_before_examples_changed",
            "created_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = get_manifest_path(config.bot_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))
        # Monkey-patch verify_model to pass (we only test retrain detection)
        monkeypatch.setattr(
            "loko.bot.classifier.manifest.verify_model",
            lambda bot_id: type("V", (), {"ok": True, "errors": [], "error_code": None})(),
        )
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "model_integrity"
        assert body["code"] == "retrain_required"

    def test_business_validation_stays_400(self, client, admin_headers, tmp_path, monkeypatch):
        """Business errors (missing hors_perimetre) remain 400, not 422."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        config = BotConfig(
            name="BadBot",
            intents=[
                Intent(id="livraison", label="Livraison", definition="D",
                       examples=[f"ex {i}" for i in range(10)]),
                # Missing hors_perimetre → business validation error
            ],
        )
        save_bot_config(config)
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 400

    def test_no_disk_path_in_422(self, client, admin_headers, tmp_path, monkeypatch):
        """422 response must not leak filesystem paths."""
        config = _make_bot(tmp_path, monkeypatch)
        resp = client.post(f"/api/bot/{config.bot_id}/publish", headers=admin_headers)
        assert resp.status_code == 422
        body_str = json.dumps(resp.json())
        # Should not contain temp path or common system paths
        assert str(tmp_path) not in body_str
        assert "/data/bots/" not in body_str
