"""E2 — Tests for OOD (Out-of-Distribution) rejection.

Acceptance criteria from SPEC_LOT_E2_HORS_PERIMETRE_OOD_LOKO.md:
  E2-A5: Determinism — centroid computation is reproducible
  E2-A6: Latency — OOD score computation < 2ms
  E2-A8: No calibration leak — OOD threshold calibrated on train only
  E2-A9: Compatibility — hors_perimetre intent still in config
  E2-A10: Traceability — ood_score in trace events
"""

from __future__ import annotations

import math
import time
import pytest


# ---------------------------------------------------------------------------
# Unit tests: ood.py
# ---------------------------------------------------------------------------


class TestComputeCentroids:
    """E2: centroid computation from embeddings."""

    def test_single_class_centroid(self):
        from loko.bot.classifier.ood import compute_centroids

        embeddings = [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
        labels = ["a", "a"]
        centroids = compute_centroids(embeddings, labels)

        assert "a" in centroids
        # Centroid of two identical vectors is the same vector (normalized)
        assert centroids["a"][0] == pytest.approx(1.0, abs=1e-6)
        assert centroids["a"][1] == pytest.approx(0.0, abs=1e-6)
        assert centroids["a"][2] == pytest.approx(0.0, abs=1e-6)

    def test_two_classes(self):
        from loko.bot.classifier.ood import compute_centroids

        embeddings = [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.8, 0.2],
            [0.2, 0.8],
        ]
        labels = ["a", "b", "a", "b"]
        centroids = compute_centroids(embeddings, labels)

        assert len(centroids) == 2
        assert "a" in centroids
        assert "b" in centroids

    def test_centroids_are_normalized(self):
        from loko.bot.classifier.ood import compute_centroids

        embeddings = [
            [3.0, 4.0],
            [6.0, 8.0],
        ]
        labels = ["a", "a"]
        centroids = compute_centroids(embeddings, labels)

        norm = math.sqrt(sum(x * x for x in centroids["a"]))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_deterministic(self):
        """E2-A5: centroid computation must be deterministic."""
        from loko.bot.classifier.ood import compute_centroids

        embeddings = [
            [0.5, 0.3, 0.1],
            [0.1, 0.7, 0.2],
            [0.3, 0.5, 0.4],
        ]
        labels = ["a", "b", "a"]

        c1 = compute_centroids(embeddings, labels)
        c2 = compute_centroids(embeddings, labels)

        for cls_id in c1:
            for v1, v2 in zip(c1[cls_id], c2[cls_id]):
                assert v1 == v2  # Exact equality, not approx


class TestOodScore:
    """E2: OOD novelty score computation."""

    def test_in_distribution_low_score(self):
        """A point identical to a centroid should have score ~0."""
        from loko.bot.classifier.ood import ood_score

        centroids = {"a": [1.0, 0.0, 0.0]}
        score = ood_score([1.0, 0.0, 0.0], centroids)
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_high_score(self):
        """A point orthogonal to all centroids should have score ~1."""
        from loko.bot.classifier.ood import ood_score

        centroids = {"a": [1.0, 0.0, 0.0]}
        score = ood_score([0.0, 1.0, 0.0], centroids)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_opposite_direction(self):
        """A point opposite to a centroid should have score ~2."""
        from loko.bot.classifier.ood import ood_score

        centroids = {"a": [1.0, 0.0, 0.0]}
        score = ood_score([-1.0, 0.0, 0.0], centroids)
        assert score == pytest.approx(2.0, abs=1e-6)

    def test_multiple_centroids_uses_nearest(self):
        """Score should use the closest centroid."""
        from loko.bot.classifier.ood import ood_score

        centroids = {
            "a": [1.0, 0.0, 0.0],
            "b": [0.0, 1.0, 0.0],
        }
        # Point close to centroid "b"
        score = ood_score([0.1, 0.9, 0.0], centroids)
        # Should be close to 0 (near centroid b)
        assert score < 0.2

    def test_latency_under_2ms(self):
        """E2-A6: OOD score computation < 2ms even for 384-dim vectors."""
        from loko.bot.classifier.ood import ood_score

        dim = 384  # MiniLM embedding dimension
        centroids = {f"cls_{i}": [0.1] * dim for i in range(10)}
        embedding = [0.05] * dim

        times = []
        for _ in range(100):
            start = time.perf_counter()
            ood_score(embedding, centroids)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        assert p95 < 2.0, f"OOD score P95 latency = {p95:.2f}ms, expected < 2ms"


class TestCalibrateOodThreshold:
    """E2: OOD threshold calibration."""

    def test_separable_distributions(self):
        """When in/out are well-separated, threshold should be between them."""
        from loko.bot.classifier.ood import calibrate_ood_threshold

        centroids = {"a": [1.0, 0.0]}

        # In-distribution: close to centroid
        in_embeddings = [[0.95, 0.05], [0.9, 0.1], [0.85, 0.15]]
        # Out-distribution: far from centroid
        out_embeddings = [[0.1, 0.9], [0.0, 1.0], [0.05, 0.95]]

        threshold, info = calibrate_ood_threshold(
            in_embeddings, out_embeddings, centroids
        )

        # Threshold should be between the score ranges
        assert info["best_f1"] > 0.8
        assert threshold > 0.0
        assert threshold < 1.5

    def test_no_out_examples_defaults(self):
        """When no OOD examples, should return default threshold."""
        from loko.bot.classifier.ood import calibrate_ood_threshold

        centroids = {"a": [1.0, 0.0]}
        in_embeddings = [[0.9, 0.1]]
        out_embeddings = []

        threshold, info = calibrate_ood_threshold(
            in_embeddings, out_embeddings, centroids
        )
        assert info["method"] == "default"

    def test_calibration_on_train_only(self):
        """E2-A8: calibration must only use provided in/out sets (no held-out)."""
        from loko.bot.classifier.ood import calibrate_ood_threshold

        centroids = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        in_embeddings = [[0.9, 0.1], [0.1, 0.9]]
        out_embeddings = [[0.5, 0.5]]

        # Function signature only accepts in/out embeddings — cannot leak held-out
        threshold, info = calibrate_ood_threshold(
            in_embeddings, out_embeddings, centroids
        )
        assert info["method"] == "f1_maximization_train_only"


class TestSaveLoadCentroids:
    """E2: centroid persistence."""

    def test_round_trip(self, tmp_path):
        from loko.bot.classifier.ood import load_centroids, save_centroids

        centroids = {
            "a": [0.1, 0.2, 0.3],
            "b": [0.4, 0.5, 0.6],
        }
        hash1 = save_centroids(centroids, tmp_path)
        loaded = load_centroids(tmp_path)

        assert loaded is not None
        assert set(loaded.keys()) == {"a", "b"}
        for cls_id in centroids:
            for v1, v2 in zip(centroids[cls_id], loaded[cls_id]):
                assert v1 == pytest.approx(v2)

    def test_deterministic_hash(self, tmp_path):
        """E2-A5: same centroids produce same hash."""
        from loko.bot.classifier.ood import save_centroids

        centroids = {"a": [0.1, 0.2], "b": [0.3, 0.4]}
        h1 = save_centroids(centroids, tmp_path)
        h2 = save_centroids(centroids, tmp_path)
        assert h1 == h2

    def test_missing_file_returns_none(self, tmp_path):
        from loko.bot.classifier.ood import load_centroids

        result = load_centroids(tmp_path / "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Integration: ClassifierAdapter with OOD
# ---------------------------------------------------------------------------


class TestClassifierAdapterOOD:
    """E2: SetFitClassifierAdapter with OOD rejection."""

    def test_ood_disabled_by_default(self):
        """Without OOD config, adapter behaves normally."""
        from loko.bot.classifier.loader import SetFitClassifierAdapter

        class MockClassifier:
            def classify(self, text, top_k=5):
                return [("livraison", 0.9), ("billing", 0.1)]

            def encode(self, texts):
                return [[0.5] * 10 for _ in texts]

        adapter = SetFitClassifierAdapter("test-bot", MockClassifier())
        assert not adapter.ood_enabled
        assert adapter.last_ood_score is None

        scores = adapter.classify_l1("test")
        assert scores[0][0] == "livraison"
        assert adapter.last_ood_score is None

    def test_ood_rejects_distant_point(self):
        """OOD-enabled adapter rejects points far from all centroids."""
        from loko.bot.classifier.loader import SetFitClassifierAdapter

        class MockClassifier:
            def classify(self, text, top_k=5):
                return [("livraison", 0.9)]

            def encode(self, texts):
                # Return a point orthogonal to centroids
                return [[0.0, 1.0, 0.0] for _ in texts]

        centroids = {"livraison": [1.0, 0.0, 0.0]}
        adapter = SetFitClassifierAdapter(
            "test-bot",
            MockClassifier(),
            ood_centroids=centroids,
            ood_threshold=0.5,
        )

        assert adapter.ood_enabled
        scores = adapter.classify_l1("something OOD")
        assert scores[0][0] == "hors_perimetre"
        assert adapter.last_ood_score is not None
        assert adapter.last_ood_score >= 0.5

    def test_ood_passes_close_point(self):
        """OOD-enabled adapter passes points close to centroids."""
        from loko.bot.classifier.loader import SetFitClassifierAdapter

        class MockClassifier:
            def classify(self, text, top_k=5):
                return [("livraison", 0.9), ("billing", 0.1)]

            def encode(self, texts):
                # Return a point close to the livraison centroid
                return [[0.95, 0.05, 0.0] for _ in texts]

        centroids = {"livraison": [1.0, 0.0, 0.0]}
        adapter = SetFitClassifierAdapter(
            "test-bot",
            MockClassifier(),
            ood_centroids=centroids,
            ood_threshold=0.5,
        )

        scores = adapter.classify_l1("livraison query")
        assert scores[0][0] == "livraison"
        assert adapter.last_ood_score is not None
        assert adapter.last_ood_score < 0.5


# ---------------------------------------------------------------------------
# Integration: Decision flow with OOD
# ---------------------------------------------------------------------------


class TestDecisionWithOOD:
    """E2: OOD rejection integrates correctly with decide_l1."""

    def test_ood_rejection_produces_reject_decision(self):
        """When OOD returns hors_perimetre, decide_l1 produces reject."""
        from loko.bot.decision import decide_l1
        from loko.bot.models import JourneyParams

        journey = JourneyParams(seuil_haut=0.85, seuil_bas=0.50)

        # Simulate OOD rejection output
        ood_scores = [("hors_perimetre", 0.85)]
        decision = decide_l1(ood_scores, journey)

        assert decision.type == "reject"
        assert decision.intent == "hors_perimetre"

    def test_ood_escalation_on_reformulation(self):
        """On 2nd attempt (reformulation), OOD should escalate, not reject."""
        from loko.bot.decision import decide_l1
        from loko.bot.models import JourneyParams

        journey = JourneyParams(seuil_haut=0.85, seuil_bas=0.50)
        ood_scores = [("hors_perimetre", 0.85)]
        decision = decide_l1(ood_scores, journey, is_reformulation=True)

        assert decision.type == "escalate"
        assert decision.intent == "hors_perimetre"


# ---------------------------------------------------------------------------
# Compatibility: E2-A9
# ---------------------------------------------------------------------------


class TestE2Compatibility:
    """E2-A9: hors_perimetre intent remains in config."""

    def test_published_bot_still_requires_hors_perimetre(self):
        """The hors_perimetre intent is still required for published bots."""
        from loko.bot.models import BotConfig, Intent

        # A bot without hors_perimetre should fail validation
        intents_without_hp = [
            Intent(
                id="livraison",
                label="Livraison",
                definition="Questions de livraison",
                examples=[f"livraison ex {i}" for i in range(10)],
            ),
            Intent(
                id="demande_conseiller",
                label="DC",
                definition="DC",
                examples=["dc"],
                is_system=True,
            ),
        ]

        # This should still fail (hors_perimetre is required)
        with pytest.raises(Exception):
            BotConfig(
                name="TestBot",
                intents=intents_without_hp,
                status="published",
            )


# ---------------------------------------------------------------------------
# Training integration: E2
# ---------------------------------------------------------------------------


class TestTrainingExcludesHorsPerimetre:
    """E2: prepare_l1_training_data excludes hors_perimetre when asked."""

    def test_exclude_hors_perimetre(self):
        from loko.bot.classifier.setfit_service import prepare_l1_training_data
        from loko.bot.models import BotConfig, Intent

        config = BotConfig(
            name="TestBot",
            intents=[
                Intent(
                    id="livraison",
                    label="Livraison",
                    definition="Questions de livraison",
                    examples=[f"livraison ex {i}" for i in range(10)],
                ),
                Intent(
                    id="hors_perimetre",
                    label="HP",
                    definition="HP",
                    examples=[f"hp ex {i}" for i in range(10)],
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

        # Without exclusion
        texts_all, labels_all = prepare_l1_training_data(config)
        assert "hors_perimetre" in labels_all

        # With exclusion
        texts_excl, labels_excl = prepare_l1_training_data(
            config, exclude_hors_perimetre=True
        )
        assert "hors_perimetre" not in labels_excl
        assert len(texts_excl) < len(texts_all)

    def test_prepare_ood_validation_data(self):
        from loko.bot.classifier.setfit_service import prepare_ood_validation_data
        from loko.bot.models import BotConfig, Intent

        config = BotConfig(
            name="TestBot",
            intents=[
                Intent(
                    id="livraison",
                    label="Livraison",
                    definition="Questions de livraison",
                    examples=[f"livraison ex {i}" for i in range(10)],
                ),
                Intent(
                    id="hors_perimetre",
                    label="HP",
                    definition="HP",
                    examples=[f"hp ex {i}" for i in range(10)],
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

        ood_texts = prepare_ood_validation_data(config)
        assert len(ood_texts) == 10
        assert all("hp ex" in t for t in ood_texts)


# ---------------------------------------------------------------------------
# TraceEvent: E2-A10
# ---------------------------------------------------------------------------


class TestTraceEventOodScore:
    """E2-A10: ood_score field in TraceEvent."""

    def test_ood_score_field_exists(self):
        from loko.bot.models import TraceEvent

        event = TraceEvent(
            turn_id="turn-1",
            step="classification_l1",
            ood_score=0.42,
        )
        assert event.ood_score == 0.42

    def test_ood_score_default_none(self):
        from loko.bot.models import TraceEvent

        event = TraceEvent(
            turn_id="turn-1",
            step="classification_l1",
        )
        assert event.ood_score is None

    def test_ood_score_serializes(self):
        from loko.bot.models import TraceEvent

        event = TraceEvent(
            turn_id="turn-1",
            step="classification_l1",
            ood_score=0.73,
        )
        data = event.model_dump(mode="json")
        assert data["ood_score"] == 0.73


# ---------------------------------------------------------------------------
# Manifest: OOD block
# ---------------------------------------------------------------------------


class TestManifestOodBlock:
    """E2: OOD block in manifest."""

    def test_write_manifest_with_ood(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

        from loko.bot.classifier.manifest import (
            LevelInfo,
            read_manifest,
            write_manifest,
        )

        bot_id = "test-ood-bot"

        # Create bot directory structure
        bot_dir = tmp_path / "bots" / bot_id / "models"
        bot_dir.mkdir(parents=True)

        ood_data = {
            "threshold": 0.35,
            "method": "centroid_cosine_distance",
            "centroids_hash": "abc123",
            "n_classes": 8,
            "calibration": {"method": "f1_maximization_train_only"},
        }

        write_manifest(
            bot_id=bot_id,
            levels={
                "level1": LevelInfo(files={}, labels=["a", "b"], n_train_examples=20)
            },
            dataset_hash="test-hash",
            ood=ood_data,
        )

        manifest = read_manifest(bot_id)
        assert manifest is not None
        assert "ood" in manifest
        assert manifest["ood"]["threshold"] == 0.35
        assert manifest["ood"]["method"] == "centroid_cosine_distance"
        assert manifest["ood"]["centroids_hash"] == "abc123"
        assert manifest["ood"]["n_classes"] == 8
