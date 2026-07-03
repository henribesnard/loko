"""Tests for the classifier module — training data, model store, and service."""

from __future__ import annotations

import pytest
from pathlib import Path

from loko.bot.classifier.builtin_examples import (
    DEMANDE_CONSEILLER_EXAMPLES,
    HORS_PERIMETRE_FALLBACK_EXAMPLES,
)
from loko.bot.classifier.model_store import (
    delete_model,
    get_model_dir,
    list_models,
    model_exists,
)
from loko.bot.classifier.setfit_service import (
    prepare_l1_training_data,
    prepare_l2_training_data,
)
from loko.bot.models import BotConfig, Intent, SubMotif, ToneProfile


# ---------------------------------------------------------------------------
# Built-in examples
# ---------------------------------------------------------------------------

class TestBuiltinExamples:
    def test_demande_conseiller_has_enough_examples(self):
        assert len(DEMANDE_CONSEILLER_EXAMPLES) >= 20

    def test_demande_conseiller_has_fr_and_en(self):
        # At least some FR and some EN examples (heuristic detection)
        fr_count = sum(1 for e in DEMANDE_CONSEILLER_EXAMPLES if any(c in e for c in "éèêàùç"))
        en_count = sum(1 for e in DEMANDE_CONSEILLER_EXAMPLES if e.startswith("I ") or "speak" in e.lower() or "please" in e.lower())
        assert fr_count >= 5
        assert en_count >= 5

    def test_hors_perimetre_fallback_exists(self):
        assert len(HORS_PERIMETRE_FALLBACK_EXAMPLES) >= 8


# ---------------------------------------------------------------------------
# Training data preparation
# ---------------------------------------------------------------------------

class TestPrepareL1Data:
    def _make_config(self) -> BotConfig:
        return BotConfig(
            name="Test",
            intents=[
                Intent(
                    id="livraison", label="Livraison", definition="Livraison",
                    examples=[f"livraison ex {i}" for i in range(10)],
                ),
                Intent(
                    id="facturation", label="Facturation", definition="Facturation",
                    examples=[f"facture ex {i}" for i in range(8)],
                ),
                Intent(
                    id="hors_perimetre", label="Hors perimetre", definition="HP",
                    examples=["blague", "meteo"], is_system=True,
                ),
                Intent(
                    id="demande_conseiller", label="Conseiller", definition="Conseiller",
                    examples=["un humain"], is_system=True,
                ),
            ],
        )

    def test_returns_all_examples(self):
        config = self._make_config()
        texts, labels = prepare_l1_training_data(config)
        # 10 + 8 + 2 + 1 + builtin demande_conseiller (minus overlap)
        assert len(texts) == len(labels)
        assert len(texts) >= 20  # at least base examples

    def test_merges_builtin_demande_conseiller(self):
        config = self._make_config()
        texts, labels = prepare_l1_training_data(config)
        dc_count = sum(1 for l in labels if l == "demande_conseiller")
        # 1 user example + builtins (with dedup)
        assert dc_count >= len(DEMANDE_CONSEILLER_EXAMPLES)

    def test_no_duplicate_examples(self):
        config = self._make_config()
        texts, _ = prepare_l1_training_data(config)
        assert len(texts) == len(set(texts))


class TestPrepareL2Data:
    def test_returns_submotif_examples(self):
        intent = Intent(
            id="livraison", label="Livraison", definition="Livraison",
            examples=[f"ex {i}" for i in range(8)],
            sub_motifs=[
                SubMotif(id="suivi", label="Suivi", definition="Suivi",
                         examples=["a", "b", "c"]),
                SubMotif(id="retard", label="Retard", definition="Retard",
                         examples=["d", "e", "f"]),
            ],
        )
        texts, labels = prepare_l2_training_data(intent)
        assert len(texts) == 6
        assert set(labels) == {"suivi", "retard"}


# ---------------------------------------------------------------------------
# Model store
# ---------------------------------------------------------------------------

class TestModelStore:
    def test_get_model_dir_level1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        d = get_model_dir("bot-1", "level1")
        assert d.exists()
        assert "level1" in str(d)

    def test_get_model_dir_level2(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        d = get_model_dir("bot-1", "level2", "livraison")
        assert d.exists()
        assert "level2_livraison" in str(d)

    def test_model_exists_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        assert not model_exists("bot-1", "level1")

    def test_model_exists_true(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        d = get_model_dir("bot-1", "level1")
        (d / "config.json").write_text("{}")
        assert model_exists("bot-1", "level1")

    def test_delete_model(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        d = get_model_dir("bot-1", "level1")
        (d / "config.json").write_text("{}")
        delete_model("bot-1", "level1")
        assert not d.exists()

    def test_list_models(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        d1 = get_model_dir("bot-1", "level1")
        (d1 / "config.json").write_text("{}")
        d2 = get_model_dir("bot-1", "level2", "livraison")
        (d2 / "config.json").write_text("{}")

        models = list_models("bot-1")
        assert len(models) == 2

    def test_invalid_level_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            get_model_dir("bot-1", "level2")  # missing intent_id


# ---------------------------------------------------------------------------
# SetFit training + inference (integration — needs ML dependencies)
# ---------------------------------------------------------------------------

class TestSetFitIntegration:
    """These tests actually train a small SetFit model.

    They require setfit + sentence-transformers installed.
    Skipped if not available.
    """

    @pytest.fixture(autouse=True)
    def _setup_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    @pytest.fixture
    def mini_data(self):
        texts = [
            "ou est mon colis", "suivi de commande", "livraison en cours",
            "je veux ma facture", "probleme de paiement", "montant incorrect",
            "retourner un article", "renvoi produit", "remboursement",
        ]
        labels = [
            "livraison", "livraison", "livraison",
            "facturation", "facturation", "facturation",
            "retour", "retour", "retour",
        ]
        return texts, labels

    @pytest.mark.slow
    def test_train_and_classify(self, mini_data):
        pytest.importorskip("setfit")
        from loko.bot.classifier.setfit_service import SetFitClassifier

        texts, labels = mini_data
        clf = SetFitClassifier("test-bot", "level1")
        result = clf.train(texts, labels, num_iterations=5, num_epochs=1)

        assert result["num_classes"] == 3
        assert result["num_samples"] == 9

        # Classify
        scores = clf.classify("ou est ma commande")
        assert len(scores) > 0
        assert scores[0][0] in ("livraison", "facturation", "retour")
        assert 0 <= scores[0][1] <= 1

    @pytest.mark.slow
    def test_save_and_reload(self, mini_data):
        pytest.importorskip("setfit")
        from loko.bot.classifier.setfit_service import SetFitClassifier

        texts, labels = mini_data
        clf = SetFitClassifier("test-bot", "level1")
        clf.train(texts, labels, num_iterations=5, num_epochs=1)

        # Reload
        clf2 = SetFitClassifier("test-bot", "level1")
        assert clf2.load()
        assert clf2.is_loaded

        scores = clf2.classify("facture")
        assert len(scores) > 0

    @pytest.mark.slow
    def test_classify_without_load_raises(self):
        pytest.importorskip("setfit")
        from loko.bot.classifier.setfit_service import SetFitClassifier

        clf = SetFitClassifier("test-bot", "level1")
        with pytest.raises(RuntimeError, match="Model not loaded"):
            clf.classify("test")
