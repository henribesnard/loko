"""Tests for M1 — Structured advice with verbatims.

Covers:
  - Overlapping dataset → advice non-empty, correct pair, verbatims present
  - Perfectly separable dataset → advice=[] for pair types
  - Merge/sort: CV + margin entries combined, sorted by severity
  - _generate_advice produces structured dicts
"""

from __future__ import annotations

from typing import Any


from loko.bot.classifier.training import (
    _generate_advice,
    _merge_and_sort_advice,
)


class TestGenerateAdvice:
    """M1: _generate_advice returns structured dicts."""

    def test_confused_pair_from_cv(self):
        """Off-diagonal >= 2 produces a confused_pair entry."""
        class_names = ["A", "B"]
        cm = [[8, 3], [1, 10]]  # A->B: 3 errors (>= 2)
        class_counts = {"A": 11, "B": 11}
        per_class_f1 = {"A": 0.8, "B": 0.9}

        advice = _generate_advice(class_names, cm, class_counts, per_class_f1)
        pair_entries = [a for a in advice if a.get("type") == "confused_pair"]

        assert len(pair_entries) >= 1
        entry = pair_entries[0]
        assert entry["evidence"] == "cv"
        assert sorted(entry["pair"]) == ["A", "B"]
        assert entry["n_exemples_faibles"] == 3
        assert "suggestion" in entry

    def test_no_pair_if_diagonal_clean(self):
        """Perfect diagonal → no confused_pair."""
        class_names = ["A", "B"]
        cm = [[10, 0], [0, 10]]
        class_counts = {"A": 20, "B": 20}
        per_class_f1 = {"A": 1.0, "B": 1.0}

        advice = _generate_advice(class_names, cm, class_counts, per_class_f1)
        pair_entries = [a for a in advice if a.get("type") == "confused_pair"]
        assert pair_entries == []

    def test_under_represented_class(self):
        class_names = ["A"]
        cm = [[5]]
        class_counts = {"A": 5}
        per_class_f1 = {"A": 1.0}

        advice = _generate_advice(class_names, cm, class_counts, per_class_f1)
        ur_entries = [a for a in advice if a.get("type") == "under_represented"]
        assert len(ur_entries) == 1
        assert ur_entries[0]["intent"] == "A"

    def test_low_f1_class(self):
        class_names = ["A", "B"]
        cm = [[3, 5], [5, 3]]
        class_counts = {"A": 20, "B": 20}
        per_class_f1 = {"A": 0.3, "B": 0.3}

        advice = _generate_advice(class_names, cm, class_counts, per_class_f1)
        f1_entries = [a for a in advice if a.get("type") == "low_f1"]
        assert len(f1_entries) == 2


class TestMergeAndSortAdvice:
    """M1: _merge_and_sort_advice merges CV + margin entries."""

    def test_merge_same_pair(self):
        """Same pair in both CV and margin → merged with evidence='both'."""
        cv = [{
            "type": "confused_pair",
            "pair": ["A", "B"],
            "evidence": "cv",
            "n_exemples_faibles": 3,
            "suggestion": "CV confusion.",
        }]
        margin = [{
            "type": "confused_pair",
            "pair": ["A", "B"],
            "evidence": "margins",
            "n_exemples_faibles": 5,
            "avg_margin": 0.05,
            "suggestion": "Margin confusion.",
            "verbatims": ["text1", "text2"],
        }]

        merged = _merge_and_sort_advice(cv, margin)
        pair_entries = [a for a in merged if a.get("type") == "confused_pair"]
        assert len(pair_entries) == 1
        entry = pair_entries[0]
        assert entry["evidence"] == "both"
        assert entry["n_exemples_faibles"] == 5  # max of 3 and 5
        assert "verbatims" in entry

    def test_disjoint_pairs(self):
        """Different pairs → both preserved."""
        cv = [{
            "type": "confused_pair",
            "pair": ["A", "B"],
            "evidence": "cv",
            "n_exemples_faibles": 3,
            "suggestion": "AB.",
        }]
        margin = [{
            "type": "confused_pair",
            "pair": ["C", "D"],
            "evidence": "margins",
            "n_exemples_faibles": 2,
            "avg_margin": 0.1,
            "suggestion": "CD.",
            "verbatims": ["x"],
        }]

        merged = _merge_and_sort_advice(cv, margin)
        pair_entries = [a for a in merged if a.get("type") == "confused_pair"]
        assert len(pair_entries) == 2

    def test_sort_by_severity(self):
        """confused_pair sorted first by n_exemples_faibles desc."""
        entries: list[dict[str, Any]] = [
            {"type": "under_represented", "intent": "X", "n_exemples_faibles": 3, "suggestion": "x"},
            {"type": "confused_pair", "pair": ["A", "B"], "evidence": "margins",
             "n_exemples_faibles": 2, "suggestion": "small"},
            {"type": "confused_pair", "pair": ["C", "D"], "evidence": "cv",
             "n_exemples_faibles": 7, "suggestion": "big"},
        ]
        merged = _merge_and_sort_advice(entries, [])

        # confused_pairs first, sorted by n_exemples_faibles desc
        assert merged[0]["pair"] == ["C", "D"]
        assert merged[1]["pair"] == ["A", "B"]
        assert merged[2]["type"] == "under_represented"

    def test_empty_inputs(self):
        assert _merge_and_sort_advice([], []) == []

    def test_margin_only(self):
        """Margin advice without any CV advice."""
        margin = [{
            "type": "confused_pair",
            "pair": ["A", "B"],
            "evidence": "margins",
            "n_exemples_faibles": 4,
            "avg_margin": 0.08,
            "suggestion": "Pair AB.",
            "verbatims": ["v1", "v2"],
        }]

        merged = _merge_and_sort_advice([], margin)
        assert len(merged) == 1
        assert merged[0]["evidence"] == "margins"
        assert merged[0]["verbatims"] == ["v1", "v2"]
