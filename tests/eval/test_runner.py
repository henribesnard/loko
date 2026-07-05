"""Tests for loko-eval runner — L1 corrections.

Covers:
  - L1.1: errors.csv schema (correct field included, no crash)
  - L1.2: check_expected_behavior on 5 grammar forms (T01-T15 fixtures)
  - L1.3: report.json deterministic (no duration_s), meta.json separate
  - L1.4: exit code from threshold, not crash; all artefacts written
  - L1.5: double run → report.json binary-identical
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from loko.eval.decision import Decision
from loko.eval.runner import (
    EvalReport,
    EvalRow,
    _ERRORS_CSV_FIELDNAMES,
    check_expected_behavior,
    write_report,
)


# ---------------------------------------------------------------------------
# L1.2 — check_expected_behavior: parametrized on T01-T15 pieges fixtures
# ---------------------------------------------------------------------------

class TestCheckExpectedBehavior:
    """L1.2: pieges expected_behavior grammar parser."""

    # --- route:{intent} ---

    @pytest.mark.parametrize("expected,decision,want", [
        # T01: route:services_en_ligne — route correct
        (
            "route:services_en_ligne",
            Decision(type="route", intent="services_en_ligne", score=0.9),
            True,
        ),
        # T01: route:services_en_ligne — wrong intent
        (
            "route:services_en_ligne",
            Decision(type="route", intent="cotisations", score=0.9),
            False,
        ),
        # T01: route:services_en_ligne — type is not route
        (
            "route:services_en_ligne",
            Decision(type="reject", intent="services_en_ligne", score=0.3),
            False,
        ),
        # T02: route:services_en_ligne
        (
            "route:services_en_ligne",
            Decision(type="route", intent="services_en_ligne", score=0.85),
            True,
        ),
        # T07: route:justificatif_droits
        (
            "route:justificatif_droits",
            Decision(type="route", intent="justificatif_droits", score=0.92),
            True,
        ),
        # T08: route:arret_travail
        (
            "route:arret_travail",
            Decision(type="route", intent="arret_travail", score=0.88),
            True,
        ),
        # T09: route:teletransmission_noemie
        (
            "route:teletransmission_noemie",
            Decision(type="route", intent="teletransmission_noemie", score=0.91),
            True,
        ),
        # T10: route:resiliation
        (
            "route:resiliation",
            Decision(type="route", intent="resiliation", score=0.87),
            True,
        ),
        # T14: route:teletransmission_noemie
        (
            "route:teletransmission_noemie",
            Decision(type="route", intent="teletransmission_noemie", score=0.75),
            True,
        ),
        # T15: route:services_en_ligne
        (
            "route:services_en_ligne",
            Decision(type="route", intent="services_en_ligne", score=0.78),
            True,
        ),
    ])
    def test_route(self, expected, decision, want):
        assert check_expected_behavior(expected, decision) is want

    # --- clarify_intra:{intent} ---

    @pytest.mark.parametrize("expected,decision,want", [
        # T03: clarify_intra:services_en_ligne — route to correct intent (acceptable)
        (
            "clarify_intra:services_en_ligne",
            Decision(type="route", intent="services_en_ligne", score=0.85),
            True,
        ),
        # T03: clarify_intra:services_en_ligne — clarify_inter with intent in candidates
        (
            "clarify_intra:services_en_ligne",
            Decision(
                type="clarify_inter", intent="services_en_ligne", score=0.6,
                candidates=[("services_en_ligne", 0.6), ("cotisations", 0.3)],
            ),
            True,
        ),
        # T03: clarify_intra — wrong intent routed
        (
            "clarify_intra:services_en_ligne",
            Decision(type="route", intent="cotisations", score=0.9),
            False,
        ),
        # T03: clarify_intra — clarify_inter without expected intent
        (
            "clarify_intra:services_en_ligne",
            Decision(
                type="clarify_inter", intent="cotisations", score=0.6,
                candidates=[("cotisations", 0.6), ("arret_travail", 0.3)],
            ),
            False,
        ),
        # T03: clarify_intra — rejected
        (
            "clarify_intra:services_en_ligne",
            Decision(type="reject", intent="services_en_ligne", score=0.2),
            False,
        ),
    ])
    def test_clarify_intra(self, expected, decision, want):
        assert check_expected_behavior(expected, decision) is want

    # --- clarify_inter:{a}|{b}[|{c}] ---

    @pytest.mark.parametrize("expected,decision,want", [
        # T04: clarify_inter:changement_coordonnees|cotisations — both present
        (
            "clarify_inter:changement_coordonnees|cotisations",
            Decision(
                type="clarify_inter", intent="changement_coordonnees", score=0.65,
                candidates=[("changement_coordonnees", 0.65), ("cotisations", 0.55)],
            ),
            True,
        ),
        # T04: only one of two present
        (
            "clarify_inter:changement_coordonnees|cotisations",
            Decision(
                type="clarify_inter", intent="changement_coordonnees", score=0.65,
                candidates=[("changement_coordonnees", 0.65), ("arret_travail", 0.3)],
            ),
            False,
        ),
        # T05: clarify_inter:changement_coordonnees|cotisations — both present
        (
            "clarify_inter:changement_coordonnees|cotisations",
            Decision(
                type="clarify_inter", intent="cotisations", score=0.6,
                candidates=[("cotisations", 0.6), ("changement_coordonnees", 0.55)],
            ),
            True,
        ),
        # T06: clarify_inter:arret_travail|cotisations|justificatif_droits — 3 intents
        (
            "clarify_inter:arret_travail|cotisations|justificatif_droits",
            Decision(
                type="clarify_inter", intent="arret_travail", score=0.5,
                candidates=[
                    ("arret_travail", 0.5), ("cotisations", 0.45),
                    ("justificatif_droits", 0.4),
                ],
            ),
            True,
        ),
        # T06: only 2 of 3 present
        (
            "clarify_inter:arret_travail|cotisations|justificatif_droits",
            Decision(
                type="clarify_inter", intent="arret_travail", score=0.5,
                candidates=[("arret_travail", 0.5), ("cotisations", 0.45)],
            ),
            False,
        ),
        # Wrong type entirely
        (
            "clarify_inter:changement_coordonnees|cotisations",
            Decision(type="route", intent="changement_coordonnees", score=0.9),
            False,
        ),
    ])
    def test_clarify_inter(self, expected, decision, want):
        assert check_expected_behavior(expected, decision) is want

    # --- escalate[:{detail}] ---

    @pytest.mark.parametrize("expected,decision,want", [
        # T11: escalate:demande_explicite
        (
            "escalate:demande_explicite",
            Decision(type="escalate", intent="demande_conseiller", score=0.95),
            True,
        ),
        # escalate without detail
        (
            "escalate",
            Decision(type="escalate", intent="demande_conseiller", score=0.9),
            True,
        ),
        # escalate expected but got route
        (
            "escalate:demande_explicite",
            Decision(type="route", intent="demande_conseiller", score=0.9),
            False,
        ),
    ])
    def test_escalate(self, expected, decision, want):
        assert check_expected_behavior(expected, decision) is want

    # --- reject ---

    @pytest.mark.parametrize("expected,decision,want", [
        # T12: reject
        (
            "reject",
            Decision(type="reject", intent="hors_perimetre", score=0.85),
            True,
        ),
        # T13: reject
        (
            "reject",
            Decision(type="reject", intent="hors_perimetre", score=0.7),
            True,
        ),
        # reject expected but got clarify
        (
            "reject",
            Decision(
                type="clarify_inter", intent="hors_perimetre", score=0.5,
                candidates=[("hors_perimetre", 0.5), ("cotisations", 0.4)],
            ),
            False,
        ),
    ])
    def test_reject(self, expected, decision, want):
        assert check_expected_behavior(expected, decision) is want


# ---------------------------------------------------------------------------
# L1.1 — errors.csv schema: 'correct' field present, no crash
# ---------------------------------------------------------------------------

class TestErrorsCsv:
    """L1.1: errors.csv written correctly with 'correct' field."""

    def test_errors_csv_written_with_correct_field(self, tmp_path):
        report = EvalReport(mode="decision", dataset="test.csv", total=3, correct=1)
        report.errors = [
            EvalRow(text="test", expected="A", predicted="B", score=0.5,
                    decision_type="route", correct=False, detail="err"),
            EvalRow(text="test2", expected="A", predicted="C", score=0.4,
                    decision_type="route", correct=False, detail="err2"),
        ]
        report.accuracy = 1 / 3

        write_report(report, tmp_path)

        errors_path = tmp_path / "errors.csv"
        assert errors_path.exists()

        with open(errors_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert "correct" in rows[0]
        assert rows[0]["correct"] == "False"

    def test_errors_csv_fieldnames_match_evalrow(self):
        """Fieldnames must cover all EvalRow fields."""
        row = EvalRow(text="t", expected="A", predicted="B", score=0.5,
                      decision_type="route", correct=False, detail="d")
        row_dict = asdict(row)
        for field_name in row_dict:
            assert field_name in _ERRORS_CSV_FIELDNAMES, (
                f"EvalRow field '{field_name}' missing from _ERRORS_CSV_FIELDNAMES"
            )

    def test_no_errors_no_csv(self, tmp_path):
        """When there are no errors, errors.csv is not created."""
        report = EvalReport(mode="raw", dataset="test.csv", total=5, correct=5)
        report.accuracy = 1.0
        write_report(report, tmp_path)
        assert not (tmp_path / "errors.csv").exists()


# ---------------------------------------------------------------------------
# L1.3 — report.json deterministic (no duration_s), meta.json separate
# ---------------------------------------------------------------------------

class TestDeterminism:
    """L1.3: report.json contains no timing; meta.json has duration_s."""

    def test_report_json_no_duration(self, tmp_path):
        report = EvalReport(mode="raw", dataset="test.csv", total=5, correct=5)
        report.accuracy = 1.0
        report.duration_s = 42.5

        write_report(report, tmp_path)

        report_data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert "duration_s" not in report_data

    def test_meta_json_has_duration(self, tmp_path):
        report = EvalReport(mode="raw", dataset="test.csv", total=5, correct=5)
        report.accuracy = 1.0
        report.duration_s = 42.5

        write_report(report, tmp_path)

        meta_path = tmp_path / "meta.json"
        assert meta_path.exists()
        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta_data["duration_s"] == 42.5

    def test_double_run_report_identical(self, tmp_path):
        """L1.5: two runs with same data produce identical report.json."""
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"

        for out_dir in (dir_a, dir_b):
            report = EvalReport(mode="decision", dataset="test.csv", total=3, correct=2)
            report.accuracy = 2 / 3
            report.per_class = {"A": {"total": 2, "correct": 1, "accuracy": 0.5}}
            report.errors = [
                EvalRow(text="x", expected="A", predicted="B", score=0.4,
                        decision_type="route", correct=False, detail="d"),
            ]
            # Different durations on purpose
            report.duration_s = 1.23 if out_dir == dir_a else 9.99
            write_report(report, out_dir)

        report_a = (dir_a / "report.json").read_bytes()
        report_b = (dir_b / "report.json").read_bytes()
        assert report_a == report_b, "report.json must be binary-identical across runs"

        # meta.json should differ (different durations)
        meta_a = (dir_a / "meta.json").read_bytes()
        meta_b = (dir_b / "meta.json").read_bytes()
        assert meta_a != meta_b


# ---------------------------------------------------------------------------
# L1.4 — Exit code: all artefacts written even when accuracy < threshold
# ---------------------------------------------------------------------------

class TestWriteReportCompleteness:
    """L1.4: write_report produces all artefacts before CLI checks threshold."""

    def test_all_artefacts_written_with_errors(self, tmp_path):
        report = EvalReport(mode="decision", dataset="test.csv", total=10, correct=3)
        report.accuracy = 0.3
        report.errors = [
            EvalRow(text=f"t{i}", expected="A", predicted="B", score=0.5,
                    decision_type="route", correct=False, detail=f"d{i}")
            for i in range(7)
        ]

        write_report(report, tmp_path)

        assert (tmp_path / "report.json").exists()
        assert (tmp_path / "meta.json").exists()
        assert (tmp_path / "errors.csv").exists()

        # Verify errors.csv is readable and complete
        with open(tmp_path / "errors.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 7

    def test_raw_mode_writes_confusion(self, tmp_path):
        report = EvalReport(mode="raw", dataset="test.csv", total=4, correct=2)
        report.accuracy = 0.5
        report.confusion = {"A": {"A": 1, "B": 1}, "B": {"A": 1, "B": 1}}
        report.errors = [
            EvalRow(text="t", expected="A", predicted="B", score=0.5, correct=False),
        ]

        write_report(report, tmp_path)

        assert (tmp_path / "report.json").exists()
        assert (tmp_path / "meta.json").exists()
        assert (tmp_path / "errors.csv").exists()
        assert (tmp_path / "confusion.csv").exists()
