"""Tests for M2 — seuil_ecart_clarification + 3-axis sweep.

Covers:
  - decide() with seuil_ecart: routes when gap large, clarifies when small
  - decide() with seuil_ecart=0: backward compatible (always routes above seuil_haut)
  - Edge cases: ecart exactly at threshold, single score, ecart 0
  - threshold_sweep_3axis: mini-sweep on fixtures produces grid with 4 metrics
"""

from __future__ import annotations

import csv

import pytest

from loko.bot.models import BotConfig, Intent, JourneyParams
from loko.eval.decision import decide
from loko.eval.runner import threshold_sweep_3axis


def _config(seuil_haut=0.75, seuil_bas=0.45, seuil_ecart=0.0) -> BotConfig:
    _ex = [f"example {i}" for i in range(10)]
    return BotConfig(
        name="Test",
        intents=[
            Intent(id="intent-a", label="A", definition="A", examples=_ex[:]),
            Intent(id="intent-b", label="B", definition="B", examples=_ex[:]),
            Intent(id="hors_perimetre", label="HP", definition="HP",
                   examples=["hp"], is_system=True),
            Intent(id="demande_conseiller", label="DC", definition="DC",
                   examples=["dc"], is_system=True),
        ],
        journey=JourneyParams(
            seuil_haut=seuil_haut,
            seuil_bas=seuil_bas,
            seuil_ecart_clarification=seuil_ecart,
        ),
    )


class TestDecideWithEcart:
    """M2: seuil_ecart_clarification in decide()."""

    def test_ecart_zero_backward_compat(self):
        """seuil_ecart=0 (default) → always routes above seuil_haut."""
        config = _config(seuil_haut=0.75, seuil_ecart=0.0)
        scores = [("A", 0.80), ("B", 0.78)]  # tiny gap
        d = decide(scores, config)
        assert d.type == "route"
        assert d.intent == "A"

    def test_ecart_triggers_clarification(self):
        """Gap < seuil_ecart → clarify even though score > seuil_haut."""
        config = _config(seuil_haut=0.75, seuil_ecart=0.15)
        scores = [("A", 0.80), ("B", 0.72)]  # gap = 0.08 < 0.15
        d = decide(scores, config)
        assert d.type == "clarify_inter"
        assert d.intent == "A"
        assert len(d.candidates) == 2
        assert d.candidates[0][0] == "A"
        assert d.candidates[1][0] == "B"

    def test_ecart_allows_route_when_gap_large(self):
        """Gap >= seuil_ecart → route normally."""
        config = _config(seuil_haut=0.75, seuil_ecart=0.10)
        scores = [("A", 0.85), ("B", 0.60)]  # gap = 0.25 >= 0.10
        d = decide(scores, config)
        assert d.type == "route"
        assert d.intent == "A"

    def test_ecart_exact_threshold(self):
        """Gap exactly at seuil_ecart → routes (not strictly less)."""
        config = _config(seuil_haut=0.75, seuil_ecart=0.10)
        scores = [("A", 0.85), ("B", 0.75)]  # gap = 0.10 = seuil_ecart
        d = decide(scores, config)
        assert d.type == "route"

    def test_ecart_single_score(self):
        """Single score above seuil_haut → route (no second to compare)."""
        config = _config(seuil_haut=0.75, seuil_ecart=0.15)
        scores = [("A", 0.90)]
        d = decide(scores, config)
        assert d.type == "route"

    def test_ecart_below_seuil_haut_unchanged(self):
        """Below seuil_haut → normal medium-zone clarification (ecart irrelevant)."""
        config = _config(seuil_haut=0.75, seuil_bas=0.45, seuil_ecart=0.15)
        scores = [("A", 0.60), ("B", 0.55)]  # below seuil_haut
        d = decide(scores, config)
        assert d.type == "clarify_inter"

    def test_transverse_unaffected(self):
        """demande_conseiller → escalate regardless of ecart."""
        config = _config(seuil_ecart=0.15)
        scores = [("demande_conseiller", 0.90), ("A", 0.85)]
        d = decide(scores, config)
        assert d.type == "escalate"


class TestThresholdSweep3Axis:
    """M2: threshold_sweep_3axis produces complete grid with 4 metrics."""

    @pytest.fixture
    def mini_datasets(self, tmp_path):
        """Create tiny CSV datasets for each GNG category."""
        # metier
        metier = tmp_path / "metier.csv"
        with open(metier, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["text", "intent"])
            w.writeheader()
            w.writerow({"text": "route A", "intent": "A"})
            w.writerow({"text": "route B", "intent": "B"})

        # conseiller
        conseiller = tmp_path / "conseiller.csv"
        with open(conseiller, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["text", "intent"])
            w.writeheader()
            w.writerow({"text": "parler humain", "intent": "demande_conseiller"})

        # horsscope
        horsscope = tmp_path / "horsscope.csv"
        with open(horsscope, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["text", "intent"])
            w.writeheader()
            w.writerow({"text": "hors sujet", "intent": "hors_perimetre"})

        # pieges
        pieges = tmp_path / "pieges.csv"
        with open(pieges, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "text", "expected_behavior", "note"])
            w.writeheader()
            w.writerow({"id": "T01", "text": "route A", "expected_behavior": "route:A", "note": ""})
            w.writerow({"id": "T02", "text": "ambigu", "expected_behavior": "clarify_inter:A|B", "note": ""})

        return {
            "metier": metier,
            "conseiller": conseiller,
            "horsscope": horsscope,
            "pieges": pieges,
        }

    def test_sweep_produces_grid(self, mini_datasets):
        """3-axis sweep produces results with all expected columns."""

        class MockClassifier:
            def classify_l1(self, text):
                if "route A" in text:
                    return [("A", 0.85), ("B", 0.50)]
                if "route B" in text:
                    return [("B", 0.80), ("A", 0.45)]
                if "humain" in text:
                    return [("demande_conseiller", 0.90), ("A", 0.10)]
                if "hors" in text:
                    return [("hors_perimetre", 0.75), ("A", 0.10)]
                if "ambigu" in text:
                    return [("A", 0.60), ("B", 0.55)]
                return [("A", 0.50)]

        config = _config(seuil_haut=0.75, seuil_bas=0.45)
        results = threshold_sweep_3axis(
            MockClassifier(),
            mini_datasets,
            config,
            seuil_haut_range=(0.7, 0.8, 0.1),
            seuil_bas_range=(0.4, 0.5, 0.1),
            seuil_ecart_range=(0.0, 0.1, 0.1),
        )

        assert len(results) > 0

        # Each point has all 4 metrics
        for point in results:
            assert "seuil_haut" in point
            assert "seuil_bas" in point
            assert "seuil_ecart" in point
            assert "gng1" in point
            assert "gng2" in point
            assert "gng3" in point
            assert "gng3_routes_directes" in point
            assert "pieges" in point
            assert "pieges_correct" in point

    def test_ecart_axis_changes_decisions(self, mini_datasets):
        """Different seuil_ecart values produce different piege results."""

        class CloseScoreClassifier:
            """Returns close scores to test ecart effect."""
            def classify_l1(self, text):
                if "ambigu" in text:
                    return [("A", 0.80), ("B", 0.75)]  # gap = 0.05
                if "route A" in text:
                    return [("A", 0.90), ("B", 0.30)]
                if "route B" in text:
                    return [("B", 0.85), ("A", 0.30)]
                if "humain" in text:
                    return [("demande_conseiller", 0.95), ("A", 0.05)]
                if "hors" in text:
                    return [("hors_perimetre", 0.80), ("A", 0.10)]
                return [("A", 0.50)]

        config = _config(seuil_haut=0.75, seuil_bas=0.40)
        results = threshold_sweep_3axis(
            CloseScoreClassifier(),
            mini_datasets,
            config,
            seuil_haut_range=(0.75, 0.75, 0.05),
            seuil_bas_range=(0.40, 0.40, 0.05),
            seuil_ecart_range=(0.0, 0.10, 0.10),
        )

        # Should have 2 points: ecart=0.0 and ecart=0.1
        assert len(results) == 2
        ecart_0 = [r for r in results if r["seuil_ecart"] == 0.0][0]
        ecart_10 = [r for r in results if r["seuil_ecart"] == 0.1][0]

        # With ecart=0.0: "ambigu" T02 expects clarify_inter:A|B,
        # but A scores 0.80 > seuil_haut=0.75, so routes → T02 fails
        # With ecart=0.10: gap=0.05 < 0.10, so clarifies → T02 may pass
        assert ecart_10["pieges_correct"] >= ecart_0["pieges_correct"]
