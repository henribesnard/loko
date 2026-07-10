"""Tests for campaign tools (run_campaign, check_bot_conformity, setup_campaign_bot).

Covers:
  - T1: Protocol matrix has exactly 27 lines and 6 gates
  - T2: All lines start as FAIL (protocol v2.2 invariant)
  - T3: Gate calculation logic (all pass, mixed, all fail)
  - T4: SKIP only allowed on skippable lines
  - T5: CE-9 executor validates bot conformity
  - T6: setup_campaign_bot builds 9 intents from train.csv
  - T7: check_bot_conformity detects missing intents
  - T8: Report generation (MD + JSON) produces valid output
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest

# Import from tools/ — add tools to path
import sys

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from run_campaign import (
    TestLine,
    GateResult,
    CampaignReport,
    build_protocol_lines,
    build_gates,
    calculate_gates,
    _mark_pass,
    _mark_fail,
    generate_report_md,
    generate_report_json,
    exec_ce9,
)

from setup_campaign_bot import (
    build_intents_from_train,
    verify_conformity,
)


# ---------------------------------------------------------------------------
# T1: Protocol matrix structure
# ---------------------------------------------------------------------------

class TestProtocolMatrix:
    """T1: protocol v2.2 matrix invariants."""

    def test_protocol_has_32_lines(self):
        lines = build_protocol_lines()
        assert len(lines) == 32, f"expected 32 lines, got {len(lines)}"

    def test_protocol_has_6_gates(self):
        lines = build_protocol_lines()
        gates = build_gates(lines)
        assert len(gates) == 6, f"expected 6 gates, got {len(gates)}"

    def test_gate_ids(self):
        lines = build_protocol_lines()
        gates = build_gates(lines)
        gate_ids = [g.gate_id for g in gates]
        assert gate_ids == ["CE", "G-0", "G-1", "G-1b", "G-2", "G-3"]

    def test_all_lines_have_unique_ids(self):
        lines = build_protocol_lines()
        ids = [l.id for l in lines]
        assert len(ids) == len(set(ids)), f"duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_all_lines_have_description(self):
        lines = build_protocol_lines()
        for line in lines:
            assert line.description, f"line {line.id} has empty description"

    def test_all_lines_map_to_known_gate(self):
        known_gates = {"CE", "G-0", "G-1", "G-1b", "G-2", "G-3"}
        lines = build_protocol_lines()
        for line in lines:
            assert line.gate in known_gates, f"line {line.id} has unknown gate {line.gate}"


# ---------------------------------------------------------------------------
# T2: All lines start as FAIL
# ---------------------------------------------------------------------------

class TestLinesStartFail:
    """T2: non execute = FAIL invariant."""

    def test_all_lines_start_fail(self):
        lines = build_protocol_lines()
        for line in lines:
            assert line.verdict == "FAIL", f"line {line.id} starts as {line.verdict}"

    def test_all_lines_start_not_executed(self):
        lines = build_protocol_lines()
        for line in lines:
            assert not line.executed, f"line {line.id} starts as executed=True"


# ---------------------------------------------------------------------------
# T3: Gate calculation
# ---------------------------------------------------------------------------

class TestGateCalculation:
    """T3: gate verdicts computed from line verdicts."""

    def test_all_pass(self):
        lines = [
            TestLine("T-1", "test 1", "G-TEST", "T"),
            TestLine("T-2", "test 2", "G-TEST", "T"),
        ]
        for l in lines:
            _mark_pass(l, "ok", "")
        gates = [GateResult("G-TEST", "Test gate", ["T-1", "T-2"])]
        calculate_gates(lines, gates)
        assert gates[0].verdict == "PASS"
        assert gates[0].pass_count == 2
        assert gates[0].fail_count == 0

    def test_one_fail(self):
        lines = [
            TestLine("T-1", "test 1", "G-TEST", "T"),
            TestLine("T-2", "test 2", "G-TEST", "T"),
        ]
        _mark_pass(lines[0], "ok", "")
        # lines[1] stays FAIL
        gates = [GateResult("G-TEST", "Test gate", ["T-1", "T-2"])]
        calculate_gates(lines, gates)
        assert gates[0].verdict == "FAIL"
        assert gates[0].pass_count == 1
        assert gates[0].fail_count == 1

    def test_all_fail(self):
        lines = [
            TestLine("T-1", "test 1", "G-TEST", "T"),
            TestLine("T-2", "test 2", "G-TEST", "T"),
        ]
        gates = [GateResult("G-TEST", "Test gate", ["T-1", "T-2"])]
        calculate_gates(lines, gates)
        assert gates[0].verdict == "FAIL"
        assert gates[0].pass_count == 0
        assert gates[0].fail_count == 2

    def test_skippable_skip_doesnt_fail_gate(self):
        """A skippable line with SKIP verdict doesn't count as failure."""
        lines = [
            TestLine("T-1", "test 1", "G-TEST", "T"),
            TestLine("T-2", "test 2", "G-TEST", "T", skippable=True),
        ]
        _mark_pass(lines[0], "ok", "")
        lines[1].verdict = "SKIP"
        lines[1].executed = True
        gates = [GateResult("G-TEST", "Test gate", ["T-1", "T-2"])]
        calculate_gates(lines, gates)
        assert gates[0].verdict == "PASS"


# ---------------------------------------------------------------------------
# T4: SKIP enforcement
# ---------------------------------------------------------------------------

class TestSkipEnforcement:
    """T4: only skippable lines can be SKIP."""

    def test_only_ce8_is_skippable(self):
        lines = build_protocol_lines()
        skippable = [l for l in lines if l.skippable]
        assert len(skippable) == 1
        assert skippable[0].id == "CE-8"

    def test_non_skippable_skip_counts_as_fail_in_gate(self):
        """A non-skippable line set to SKIP is counted as FAIL by gate calc."""
        lines = [
            TestLine("T-1", "test 1", "G-TEST", "T"),
        ]
        lines[0].verdict = "SKIP"
        lines[0].skippable = False
        gates = [GateResult("G-TEST", "Test gate", ["T-1"])]
        calculate_gates(lines, gates)
        assert gates[0].verdict == "FAIL"


# ---------------------------------------------------------------------------
# T5: CE-9 executor
# ---------------------------------------------------------------------------

class TestCE9Executor:
    """T5: CE-9 validates bot conformity."""

    def _make_good_config(self, tmp_dir: Path) -> Path:
        """Create a valid bot config with 9 intents + L2."""
        intents = []
        for intent_id in [
            "help_leave", "help_contact", "help_billing",
            "help_documents", "help_cancellation", "help_account",
            "help_transfer",
        ]:
            intents.append({
                "id": intent_id,
                "label": intent_id.replace("_", " ").title(),
                "definition": f"Intent {intent_id}",
                "examples": [f"ex{i} for {intent_id}" for i in range(10)],
                "sub_motifs": [],
                "is_system": False,
            })
        # Add services_en_ligne L2 sub-motifs
        sel = next(i for i in intents if i["id"] == "help_account")
        sel["sub_motifs"] = [
            {"id": f"sub_{j}", "label": f"Sub {j}", "examples": [f"ex{k}" for k in range(3)]}
            for j in range(5)
        ]
        # System intents
        intents.append({
            "id": "hors_perimetre",
            "label": "Hors perimetre",
            "definition": "OOS",
            "examples": [f"oos{i}" for i in range(10)],
            "sub_motifs": [],
            "is_system": True,
        })
        intents.append({
            "id": "demande_conseiller",
            "label": "Demande conseiller",
            "definition": "Escalate",
            "examples": [f"conseiller{i}" for i in range(10)],
            "sub_motifs": [],
            "is_system": True,
        })
        config = {"intents": intents}
        config_path = tmp_dir / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        return tmp_dir

    def test_ce9_pass_on_valid_config(self, tmp_path):
        bot_dir = self._make_good_config(tmp_path)
        campaign_dir = tmp_path / "campaign"
        campaign_dir.mkdir()

        line = TestLine("CE-9", "Bot conformity", "CE", "CE")
        exec_ce9(line, campaign_dir, bot_dir=str(bot_dir))
        assert line.verdict == "PASS"
        assert line.executed is True

    def test_ce9_fail_on_missing_intent(self, tmp_path):
        bot_dir = self._make_good_config(tmp_path)
        # Remove demande_conseiller
        config_path = bot_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["intents"] = [i for i in config["intents"] if i["id"] != "demande_conseiller"]
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

        campaign_dir = tmp_path / "campaign"
        campaign_dir.mkdir()

        line = TestLine("CE-9", "Bot conformity", "CE", "CE")
        exec_ce9(line, campaign_dir, bot_dir=str(bot_dir))
        assert line.verdict == "FAIL"

    def test_ce9_fail_on_no_bot_dir(self, tmp_path):
        campaign_dir = tmp_path / "campaign"
        campaign_dir.mkdir()

        line = TestLine("CE-9", "Bot conformity", "CE", "CE")
        exec_ce9(line, campaign_dir)
        assert line.verdict == "FAIL"


# ---------------------------------------------------------------------------
# T6: setup_campaign_bot intents
# ---------------------------------------------------------------------------

class TestSetupCampaignBot:
    """T6: setup_campaign_bot builds correct intents."""

    def _make_train_csv(self, tmp_path: Path) -> Path:
        """Create a minimal train.csv with 8 intents (no demande_conseiller)."""
        csv_path = tmp_path / "train.csv"
        rows = []
        for intent in [
            "help_leave", "help_contact", "help_billing",
            "hors_perimetre", "help_documents", "help_cancellation",
            "help_account", "help_transfer",
        ]:
            for i in range(10):
                rows.append({"text": f"example {i} for {intent}", "intent": intent})

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["text", "intent"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def test_builds_9_intents(self, tmp_path):
        csv_path = self._make_train_csv(tmp_path)
        intents = build_intents_from_train(csv_path)
        assert len(intents) == 9

    def test_adds_demande_conseiller(self, tmp_path):
        csv_path = self._make_train_csv(tmp_path)
        intents = build_intents_from_train(csv_path)
        ids = {i["id"] for i in intents}
        assert "demande_conseiller" in ids

    def test_demande_conseiller_is_system(self, tmp_path):
        csv_path = self._make_train_csv(tmp_path)
        intents = build_intents_from_train(csv_path)
        dc = next(i for i in intents if i["id"] == "demande_conseiller")
        assert dc["is_system"] is True

    def test_services_en_ligne_has_l2(self, tmp_path):
        csv_path = self._make_train_csv(tmp_path)
        intents = build_intents_from_train(csv_path)
        sel = next(i for i in intents if i["id"] == "help_account")
        assert len(sel["sub_motifs"]) >= 5

    def test_conformity_passes(self, tmp_path):
        csv_path = self._make_train_csv(tmp_path)
        intents = build_intents_from_train(csv_path)
        errors = verify_conformity(intents)
        assert errors == [], f"conformity errors: {errors}"


# ---------------------------------------------------------------------------
# T7: Conformity check detects issues
# ---------------------------------------------------------------------------

class TestConformityDetection:
    """T7: verify_conformity detects config issues."""

    def test_missing_intent_detected(self):
        intents = [
            {"id": "help_leave", "examples": list(range(10)), "is_system": False},
        ]
        errors = verify_conformity(intents)
        assert any("Missing intents" in e for e in errors)

    def test_too_few_examples_detected(self):
        intents = [
            {"id": name, "examples": list(range(10)), "is_system": name in ("hors_perimetre", "demande_conseiller"),
             "sub_motifs": [{"id": f"s{i}"} for i in range(5)] if name == "help_account" else []}
            for name in [
                "help_leave", "help_contact", "help_billing",
                "hors_perimetre", "help_documents", "help_cancellation",
                "help_account", "help_transfer", "demande_conseiller",
            ]
        ]
        # Make one intent have too few examples
        intents[0]["examples"] = [1, 2, 3]
        errors = verify_conformity(intents)
        assert any("has 3 examples" in e for e in errors)

    def test_missing_l2_detected(self):
        intents = [
            {"id": name, "examples": list(range(10)), "is_system": name in ("hors_perimetre", "demande_conseiller"),
             "sub_motifs": []}
            for name in [
                "help_leave", "help_contact", "help_billing",
                "hors_perimetre", "help_documents", "help_cancellation",
                "help_account", "help_transfer", "demande_conseiller",
            ]
        ]
        errors = verify_conformity(intents)
        assert any("L2" in e for e in errors)


# ---------------------------------------------------------------------------
# T8: Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """T8: MD and JSON reports."""

    def _make_report(self) -> CampaignReport:
        report = CampaignReport()
        report.version = "0.3.8"
        report.commit = "abc1234"
        report.bot_id = "test-bot"
        report.lines = build_protocol_lines()
        report.gates = build_gates(report.lines)
        # Pass a few lines
        for line in report.lines:
            if line.id in ("CE-1", "CE-2"):
                _mark_pass(line, "ok", "")
        calculate_gates(report.lines, report.gates)
        return report

    def test_md_report_contains_all_lines(self):
        report = self._make_report()
        md = generate_report_md(report)
        for line in report.lines:
            assert line.id in md, f"line {line.id} not in MD report"

    def test_md_report_contains_all_gates(self):
        report = self._make_report()
        md = generate_report_md(report)
        for gate in report.gates:
            assert gate.gate_id in md, f"gate {gate.gate_id} not in MD report"

    def test_json_report_has_required_fields(self):
        report = self._make_report()
        data = generate_report_json(report)
        assert "version" in data
        assert "lines" in data
        assert "gates" in data
        assert len(data["lines"]) == 32
        assert len(data["gates"]) == 6

    def test_json_report_lines_have_verdict(self):
        report = self._make_report()
        data = generate_report_json(report)
        for line in data["lines"]:
            assert "verdict" in line
            assert line["verdict"] in ("PASS", "FAIL", "SKIP")
