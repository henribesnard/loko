"""D1 — Calibration fingerprint guard.

Verifies that the calibration fingerprint mechanism:
  (a) is deterministic (same inputs → same hash)
  (b) changes when temperature, labels, or model files change
  (c) blocks loading when fingerprint mismatches
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from loko.bot.classifier.manifest import (
    LevelInfo,
    compute_calibration_fingerprint,
    verify_calibration_fingerprint,
    write_manifest,
)


# -- Fixtures ---------------------------------------------------------------

SAMPLE_FILES = {"model.safetensors": "aaa111", "config.json": "bbb222"}
SAMPLE_LABELS = ["help_account", "help_contact", "help_documents"]
SAMPLE_TEMPERATURE = 0.60


@pytest.fixture
def sample_manifest(tmp_path: Path) -> dict:
    """Build a minimal valid manifest with calibration fingerprint."""
    bot_dir = tmp_path / "bots" / "test-bot" / "models"
    bot_dir.mkdir(parents=True)

    level1 = LevelInfo(
        files=SAMPLE_FILES,
        labels=SAMPLE_LABELS,
        n_train_examples=100,
    )

    with patch("loko.bot.classifier.manifest.get_manifest_path", return_value=bot_dir / "manifest.json"):
        write_manifest(
            bot_id="test-bot",
            levels={"level1": level1},
            dataset_hash="ddd444",
            calibration={"temperature": SAMPLE_TEMPERATURE},
        )

    manifest = json.loads((bot_dir / "manifest.json").read_text(encoding="utf-8"))
    return manifest


# -- Tests -------------------------------------------------------------------


class TestComputeCalibrationFingerprint:
    """Tests for compute_calibration_fingerprint()."""

    def test_deterministic(self):
        """Same inputs produce the same fingerprint."""
        fp1 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, SAMPLE_FILES)
        fp2 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, SAMPLE_FILES)
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_changes_on_temperature(self):
        """Different temperature → different fingerprint."""
        fp1 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, SAMPLE_FILES)
        fp2 = compute_calibration_fingerprint(1.0, SAMPLE_LABELS, SAMPLE_FILES)
        assert fp1 != fp2

    def test_changes_on_labels(self):
        """Different labels → different fingerprint."""
        fp1 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, SAMPLE_FILES)
        fp2 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS + ["help_leave"], SAMPLE_FILES)
        assert fp1 != fp2

    def test_changes_on_model_hash(self):
        """Different model file hashes → different fingerprint."""
        fp1 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, SAMPLE_FILES)
        altered_files = dict(SAMPLE_FILES)
        altered_files["model.safetensors"] = "xxx999"
        fp2 = compute_calibration_fingerprint(0.6, SAMPLE_LABELS, altered_files)
        assert fp1 != fp2

    def test_label_order_irrelevant(self):
        """Labels are sorted internally — order should not matter."""
        fp1 = compute_calibration_fingerprint(0.6, ["a", "b", "c"], SAMPLE_FILES)
        fp2 = compute_calibration_fingerprint(0.6, ["c", "a", "b"], SAMPLE_FILES)
        assert fp1 == fp2


class TestVerifyCalibrationFingerprint:
    """Tests for verify_calibration_fingerprint()."""

    def test_valid_manifest(self, sample_manifest: dict):
        """Concordant fingerprint → (True, ...)."""
        ok, detail = verify_calibration_fingerprint(sample_manifest)
        assert ok is True
        assert "matches" in detail

    def test_no_calibration(self):
        """Manifest without calibration → passes (nothing to verify)."""
        ok, _ = verify_calibration_fingerprint({"levels": {"level1": {}}})
        assert ok is True

    def test_no_fingerprint_legacy(self):
        """Legacy manifest with calibration but no fingerprint → passes."""
        manifest = {
            "calibration": {"temperature": 0.6},
            "levels": {"level1": {"labels": SAMPLE_LABELS, "files": SAMPLE_FILES}},
        }
        ok, detail = verify_calibration_fingerprint(manifest)
        assert ok is True
        assert "legacy" in detail

    def test_tampered_temperature(self, sample_manifest: dict):
        """Temperature changed without re-fingerprint → (False, ...)."""
        sample_manifest["calibration"]["temperature"] = 1.5
        ok, detail = verify_calibration_fingerprint(sample_manifest)
        assert ok is False
        assert "mismatch" in detail

    def test_tampered_labels(self, sample_manifest: dict):
        """Labels changed without re-fingerprint → (False, ...)."""
        sample_manifest["levels"]["level1"]["labels"].append("new_intent")
        ok, detail = verify_calibration_fingerprint(sample_manifest)
        assert ok is False
        assert "mismatch" in detail

    def test_tampered_model_files(self, sample_manifest: dict):
        """Model files changed without re-fingerprint → (False, ...)."""
        sample_manifest["levels"]["level1"]["files"]["model.safetensors"] = "tampered"
        ok, detail = verify_calibration_fingerprint(sample_manifest)
        assert ok is False
        assert "mismatch" in detail

    def test_missing_level1(self):
        """Calibration with fingerprint but no level1 → (False, ...)."""
        manifest = {
            "calibration": {"temperature": 0.6, "fingerprint": "abc"},
            "levels": {},
        }
        ok, detail = verify_calibration_fingerprint(manifest)
        assert ok is False
        assert "level1 missing" in detail


class TestWriteManifestInjectsFingerprint:
    """Verify that write_manifest() injects the fingerprint automatically."""

    def test_fingerprint_present_when_calibration(self, sample_manifest: dict):
        """write_manifest() with calibration produces a fingerprint field."""
        assert "fingerprint" in sample_manifest["calibration"]
        assert len(sample_manifest["calibration"]["fingerprint"]) == 64

    def test_no_fingerprint_without_calibration(self, tmp_path: Path):
        """write_manifest() without calibration has no fingerprint."""
        bot_dir = tmp_path / "bots" / "test-bot2" / "models"
        bot_dir.mkdir(parents=True)

        level1 = LevelInfo(files=SAMPLE_FILES, labels=SAMPLE_LABELS, n_train_examples=50)

        with patch("loko.bot.classifier.manifest.get_manifest_path", return_value=bot_dir / "manifest.json"):
            write_manifest(
                bot_id="test-bot2",
                levels={"level1": level1},
                dataset_hash="eee555",
            )

        manifest = json.loads((bot_dir / "manifest.json").read_text(encoding="utf-8"))
        assert "calibration" not in manifest


class TestLoaderRejectsOnMismatch:
    """Verify that load_classifier() raises on fingerprint mismatch."""

    def test_loader_raises_on_mismatch(self, tmp_path: Path):
        """load_classifier() must raise ComponentUnavailableError on mismatch."""
        from loko.bot.errors import ComponentUnavailableError

        # Build a manifest with a valid fingerprint, then tamper with temperature
        manifest = {
            "schema": 1,
            "bot_id": "test-bot-mismatch",
            "levels": {
                "level1": {
                    "files": SAMPLE_FILES,
                    "labels": SAMPLE_LABELS,
                    "n_train_examples": 100,
                }
            },
            "dataset_hash": "ddd444",
            "calibration": {
                "temperature": 0.6,
                "fingerprint": compute_calibration_fingerprint(
                    0.6, SAMPLE_LABELS, SAMPLE_FILES,
                ),
            },
        }
        # Tamper: change temperature but keep old fingerprint
        manifest["calibration"]["temperature"] = 1.5

        # Mock at source modules (imports are local inside load_classifier)
        with (
            patch("loko.bot.classifier.model_store.model_exists", return_value=True),
            patch("loko.bot.classifier.setfit_service.SetFitClassifier") as mock_clf_cls,
            patch("loko.bot.classifier.manifest.read_manifest", return_value=manifest),
        ):
            mock_clf = mock_clf_cls.return_value
            mock_clf.load.return_value = True

            from loko.bot.classifier.loader import load_classifier

            with pytest.raises(ComponentUnavailableError, match="fingerprint mismatch"):
                load_classifier("test-bot-mismatch")
