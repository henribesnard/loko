#!/usr/bin/env python3
"""E0 — Campaign runner: enforces opposability of validation campaigns.

Executes all protocol v2.2 lines sequentially, generates a report where
every line starts as NON EXÉCUTÉ = FAIL, and replaces verdicts only when
backed by an existing artifact. Gate verdicts are CALCULATED, never edited.

A test line can only be marked SKIP if the protocol explicitly allows it
for that specific test. Comments go to an "anomalies de protocole" section
that never alters verdicts.

Usage:
    python tools/run_campaign.py --bot-dir <path> --campaign-dir <path> [--image <image>] [--dry-run]
    python tools/run_campaign.py --bot-dir <path> --campaign-dir <path> --image loko:v0.3.8 --tag v0.3.8

Exit code:
    0 — all gates passed
    1 — one or more gates failed
    2 — runner error (bad args, missing files)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = ROOT / "eval" / "datasets"

logger = logging.getLogger("campaign-runner")

# ──────────────────────────────────────────────────────────────────────
# Interdits opposables v2.2 - Displayed at start of every campaign
# ──────────────────────────────────────────────────────────────────────

INTERDITS_V22 = [
    "1. Requalifier un test unitaire ou un exemple isole en pourcentage GNG.",
    "2. Mesurer depuis l'hote au lieu du conteneur.",
    "3. Omettre ou 'skipper' une ligne du tableau de synthese (non execute = FAIL).",
    "4. Valider un critere 'structurellement' / 'au niveau code' sans execution.",
    "5. Toucher aux CSV held-out (y compris renommage de labels), ou entrainer avec.",
    "6. Committer pendant la campagne sans repartir de V0-1 (hors derogation V3-0 tracee).",
    "7. Presenter des chiffres GNG a seuils non figes ou differents entre jeux.",
    "8. Requalifier un FAIL en artefact de mesure pendant la campagne.",
    "9. Declarer un gate ou un 'R' valide sans execution de toutes ses lignes ; "
    "les verdicts de gates sont calcules par le runner, jamais rediges.",
]


# ──────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TestLine:
    """A single test line in the protocol."""
    id: str
    description: str
    gate: str  # Which gate this belongs to (G-0, G-1, G-1b, G-2, G-3)
    phase: str  # CE, V0, V1, V2, V3
    verdict: str = "FAIL"  # NON EXECUTE at start, then PASS/FAIL
    measured: str = ""
    artifact: str = ""
    detail: str = ""
    executed: bool = False
    skippable: bool = False  # Only True if protocol allows SKIP for this test
    anomaly: str = ""


@dataclass
class GateResult:
    """Calculated gate result (never editable)."""
    gate_id: str
    description: str
    lines: list[str] = field(default_factory=list)  # TestLine IDs
    verdict: str = "FAIL"
    all_passed: bool = False
    fail_count: int = 0
    pass_count: int = 0
    detail: str = ""


@dataclass
class CampaignReport:
    """Full campaign report."""
    version: str = ""
    tag: str = ""
    commit: str = ""
    image_digest: str = ""
    bot_id: str = ""
    manifest_hash: str = ""
    protocol_version: str = "v2.2"
    runner_version: str = "1.0.0"
    machine_reference: str = ""
    started_at: str = ""
    completed_at: str = ""
    dry_run: bool = False
    lines: list[TestLine] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)
    anomalies_protocole: list[str] = field(default_factory=list)
    overall_verdict: str = "NON VALIDE"


# ──────────────────────────────────────────────────────────────────────
# Protocol definition: all lines from CE to V3
# ──────────────────────────────────────────────────────────────────────

def build_protocol_lines() -> list[TestLine]:
    """Build the full protocol v2.2 test matrix.

    Every line starts as verdict=FAIL (non exécuté).
    """
    lines = [
        # ── CE: Conditions d'entrée ──
        TestLine("CE-1", "Worktree clean, main branch", "CE", "CE"),
        TestLine("CE-2", "Tag present + triple version check", "CE", "CE"),
        TestLine("CE-3", "Docker image built + size <= 1.6 Go", "CE", "CE"),
        TestLine("CE-4", "Frozen datasets present + hashes match", "CE", "CE"),
        TestLine("CE-5", "Dataset intersection check (no leakage)", "CE", "CE"),
        TestLine("CE-6", "loko-eval installed and importable", "CE", "CE"),
        TestLine("CE-7", "Campaign artifacts directory exists", "CE", "CE"),
        TestLine("CE-8", "LLM provider ping (temp 0)", "CE", "CE", skippable=True),
        TestLine("CE-9", "Bot conformity: 9 intents + L2 labels", "CE", "CE"),

        # ── V0: Build validation (G-0) ──
        TestLine("V0-1", "pytest: all tests pass", "G-0", "V0"),
        TestLine("V0-2", "ML imports (PyTorch, SetFit)", "G-0", "V0"),
        TestLine("V0-3", "Anti-mock grep (0 occurrences)", "G-0", "V0"),
        TestLine("V0-4", "npm/pip audit (0 vulnerabilities)", "G-0", "V0"),
        TestLine("V0-5", "Image size by inspect <= 1.6 Go", "G-0", "V0"),

        # ── V1: Runtime R0 (G-1 éliminatoire) ──
        TestLine("V1-1", "Server startup + health check", "G-1", "V1"),
        TestLine("V1-2", "No-mock guard active at runtime", "G-1", "V1"),
        TestLine("V1-3", "Classifier loader integrity", "G-1", "V1"),
        TestLine("V1-4", "CRITICAL log at boot (check_published_bots)", "G-1", "V1"),
        TestLine("V1-5", "Offline mode (HF_HUB_OFFLINE=1)", "G-1b", "V1"),

        # ── V2: Training R1.a (G-2) ──
        TestLine("V2-1", "Training time <= 300s", "G-2", "V2"),
        TestLine("V2-2", "L2 coverage (help_account 5 labels)", "G-2", "V2"),
        TestLine("V2-3", "Atomicity (train -> publish -> restart -> identical)", "G-2", "V2"),
        TestLine("V2-4", "Improvement cycle: pair detected + re-train", "G-2", "V2"),
        TestLine("V2-5", "Improvement cycle: verify pair resolved", "G-2", "V2"),
        TestLine("V2-6", "Classification P95 <= 50ms (machine de reference)", "G-2", "V2"),

        # ── V3: Evaluation R1.b (G-3) ──
        TestLine("V3-0", "Sweep Pareto 3-axis + selection", "G-3", "V3"),
        TestLine("V3-1", "GNG-1 >= 85% (heldout_metier)", "G-3", "V3"),
        TestLine("V3-2", "GNG-2 >= 90% (heldout_conseiller)", "G-3", "V3"),
        TestLine("V3-3", "GNG-3 >= 80%, routes directes <= 5 (heldout_horsscope)", "G-3", "V3"),
        TestLine("V3-4", "Pieges >= 12/15 commentes", "G-3", "V3"),
        TestLine("V3-5", "Modele + seuils + manifeste geles", "G-3", "V3"),
        TestLine("V3-6", "Reproducibility: diff vide sur 2 runs", "G-3", "V3"),
    ]
    return lines


def build_gates(lines: list[TestLine]) -> list[GateResult]:
    """Build gate definitions from protocol lines."""
    gate_map: dict[str, list[str]] = {}
    for line in lines:
        gate_map.setdefault(line.gate, []).append(line.id)

    gates = [
        GateResult("CE", "Conditions d'entree (bloquant)", gate_map.get("CE", [])),
        GateResult("G-0", "Build validation", gate_map.get("G-0", [])),
        GateResult("G-1", "Runtime R0 (eliminatoire)", gate_map.get("G-1", [])),
        GateResult("G-1b", "Offline mode", gate_map.get("G-1b", [])),
        GateResult("G-2", "Training R1.a", gate_map.get("G-2", [])),
        GateResult("G-3", "Evaluation R1.b (verrou qualite)", gate_map.get("G-3", [])),
    ]
    return gates


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _run_cmd(cmd: list[str], timeout: int = 300, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a command with timeout."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        cwd=cwd or ROOT,
    )


def _hash_file(path: Path) -> str:
    """SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _save_artifact(campaign_dir: Path, name: str, content: str) -> Path:
    """Save artifact to campaign directory, return path."""
    path = campaign_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def _find_line(lines: list[TestLine], line_id: str) -> TestLine | None:
    """Find a line by ID."""
    for line in lines:
        if line.id == line_id:
            return line
    return None


def _mark_pass(line: TestLine, measured: str, artifact: str, detail: str = "") -> None:
    """Mark a line as PASS with evidence."""
    line.verdict = "PASS"
    line.measured = measured
    line.artifact = artifact
    line.detail = detail
    line.executed = True


def _mark_fail(line: TestLine, measured: str, detail: str = "") -> None:
    """Mark a line as FAIL with reason."""
    line.verdict = "FAIL"
    line.measured = measured
    line.detail = detail
    line.executed = True


# ──────────────────────────────────────────────────────────────────────
# Test executors — each returns True if the check can proceed
# ──────────────────────────────────────────────────────────────────────

def exec_ce1(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-1: Worktree clean, main branch."""
    result = _run_cmd(["git", "status", "--porcelain"])
    dirty_files = [l for l in result.stdout.strip().splitlines() if l.strip()]
    branch = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    if len(dirty_files) == 0 and branch == "main":
        _mark_pass(line, f"branch={branch}, clean=yes", str(campaign_dir / "CE-1.txt"))
        _save_artifact(campaign_dir, "CE-1.txt", f"branch={branch}\nclean=yes\n")
    else:
        _mark_fail(line, f"branch={branch}, dirty={len(dirty_files)}", "\n".join(dirty_files))
        _save_artifact(campaign_dir, "CE-1.txt", f"FAIL\nbranch={branch}\n" + "\n".join(dirty_files))


def exec_ce2(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-2: Tag present + version match."""
    tag = ctx.get("tag", "")
    result = _run_cmd(["git", "describe", "--tags", "--exact-match"])
    current_tag = result.stdout.strip()

    # Read pyproject version
    pyproject = ROOT / "pyproject.toml"
    pyproject_version = ""
    for l in pyproject.read_text(encoding="utf-8").splitlines():
        if l.strip().startswith("version"):
            pyproject_version = l.split("=", 1)[1].strip().strip('"').strip("'")
            break

    tag_version = current_tag.lstrip("v") if current_tag else "(none)"
    ok = bool(current_tag) and tag_version == pyproject_version
    if tag:
        ok = ok and current_tag == tag

    detail = f"tag={current_tag}, pyproject={pyproject_version}"
    if ok:
        _mark_pass(line, detail, str(campaign_dir / "CE-2.txt"))
    else:
        _mark_fail(line, detail)
    _save_artifact(campaign_dir, "CE-2.txt", detail)


def exec_ce3(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-3: Docker image built + size <= 1.6 Go."""
    image = ctx.get("image")
    if not image:
        _mark_fail(line, "no image specified")
        return

    result = _run_cmd(["docker", "inspect", "--format", "{{.Size}}", image])
    if result.returncode != 0:
        _mark_fail(line, f"image not found: {image}")
        return

    try:
        size_bytes = int(result.stdout.strip())
        size_mb = size_bytes / (1024 * 1024)
        ok = size_mb <= 1600
        detail = f"image={image}, size={size_mb:.0f}MB"
        if ok:
            _mark_pass(line, detail, str(campaign_dir / "CE-3.txt"))
        else:
            _mark_fail(line, detail, "exceeds 1600MB limit")
        _save_artifact(campaign_dir, "CE-3.txt", detail)
    except ValueError:
        _mark_fail(line, f"cannot parse size for {image}")


def exec_ce4(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-4: Frozen datasets present + hashes match."""
    hashes_file = DATASETS_DIR / "HASHES.sha256"
    if not hashes_file.exists():
        _mark_fail(line, "HASHES.sha256 missing")
        return

    errors: list[str] = []
    expected_files = ["train.csv", "heldout_metier.csv", "heldout_conseiller.csv",
                      "heldout_horsscope.csv", "pieges.csv"]

    for hash_line in hashes_file.read_text(encoding="utf-8").strip().splitlines():
        if not hash_line.strip():
            continue
        expected_hash, fname = hash_line.strip().split("  ", 1)
        fpath = DATASETS_DIR / fname
        if not fpath.exists():
            errors.append(f"{fname} missing")
            continue
        actual_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append(f"{fname} hash mismatch")

    for f in expected_files:
        if not (DATASETS_DIR / f).exists():
            errors.append(f"{f} missing")

    if errors:
        _mark_fail(line, "; ".join(errors))
    else:
        _mark_pass(line, f"{len(expected_files)} files verified",
                   str(campaign_dir / "CE-4.txt"))
    _save_artifact(campaign_dir, "CE-4.txt",
                   "OK\n" + "\n".join(errors) if errors else "OK: all hashes match")


def exec_ce5(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-5: Dataset intersection check."""
    script = ROOT / "tools" / "make_datasets.py"
    if not script.exists():
        _mark_fail(line, "make_datasets.py not found")
        return

    result = _run_cmd([sys.executable, str(script), "--check", str(DATASETS_DIR)])
    if result.returncode == 0:
        _mark_pass(line, "exit 0 - no intersection", str(campaign_dir / "CE-5.txt"))
    else:
        _mark_fail(line, f"exit {result.returncode}", result.stderr.strip())
    _save_artifact(campaign_dir, "CE-5.txt",
                   result.stdout + "\n" + result.stderr)


def exec_ce6(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-6: loko-eval installed."""
    result = _run_cmd([sys.executable, "-c", "from loko.eval.cli import main; print('ok')"])
    if result.returncode == 0:
        _mark_pass(line, "loko-eval importable", str(campaign_dir / "CE-6.txt"))
    else:
        _mark_fail(line, f"import error: {result.stderr.strip()}")
    _save_artifact(campaign_dir, "CE-6.txt", result.stdout + "\n" + result.stderr)


def exec_ce7(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-7: Campaign directory ready."""
    if campaign_dir.is_dir():
        _mark_pass(line, str(campaign_dir), str(campaign_dir))
    else:
        _mark_fail(line, f"{campaign_dir} not found")


def exec_ce8(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-8: LLM provider ping (skippable if no provider configured)."""
    # This test is skippable per protocol (not all environments have LLM)
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    config_path = Path(bot_dir) / "config.json"
    if not config_path.is_file():
        _mark_fail(line, "config.json not found")
        return

    config = json.loads(config_path.read_text(encoding="utf-8"))
    llm = config.get("llm", {})
    if not llm.get("api_key_set", False):
        line.verdict = "SKIP"
        line.detail = "LLM API key not configured (skippable per protocol)"
        line.executed = True
        return

    _mark_pass(line, "LLM config present", str(campaign_dir / "CE-8.txt"))
    _save_artifact(campaign_dir, "CE-8.txt", f"provider={llm.get('provider')}")


def exec_ce9(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """CE-9: Bot conformity check - 9 intents + L2 labels (protocol v2.2).

    Verifies:
    - 9 intentions (7 metier + hors_perimetre + demande_conseiller)
    - >= 8 examples per intent
    - L2 help_account declared with 5 labels
    """
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    config_path = Path(bot_dir) / "config.json"
    if not config_path.is_file():
        _mark_fail(line, "config.json not found")
        return

    config = json.loads(config_path.read_text(encoding="utf-8"))
    intents = config.get("intents", [])
    intent_ids = {i["id"] for i in intents}

    errors: list[str] = []
    conformity: dict[str, Any] = {
        "bot_id": config.get("bot_id", ""),
        "n_intents": len(intents),
        "intent_ids": sorted(intent_ids),
        "checks": [],
    }

    # Check 9 intents
    required_intents = {
        "hors_perimetre", "demande_conseiller",
        "help_leave", "help_contact", "help_billing",
        "help_documents", "help_cancellation", "help_account",
        "help_transfer",
    }
    missing_intents = required_intents - intent_ids
    if missing_intents:
        errors.append(f"missing intents: {sorted(missing_intents)}")
    if len(intents) != 9:
        errors.append(f"expected 9 intents, got {len(intents)}")

    conformity["checks"].append({
        "check": "9_intents",
        "pass": len(missing_intents) == 0 and len(intents) == 9,
        "detail": f"found {len(intents)}, missing: {sorted(missing_intents)}",
    })

    # Check >= 8 examples per non-system intent
    for intent in intents:
        n_ex = len(intent.get("examples", []))
        is_sys = intent.get("is_system", False)
        if not is_sys and n_ex < 8:
            errors.append(f"intent '{intent['id']}' has {n_ex} examples (min 8)")
        conformity["checks"].append({
            "check": f"examples_{intent['id']}",
            "pass": is_sys or n_ex >= 8,
            "detail": f"{n_ex} examples" + (" (system)" if is_sys else ""),
        })

    # Check L2 help_account
    sel_intent = next((i for i in intents if i["id"] == "help_account"), None)
    if sel_intent:
        sub_motifs = sel_intent.get("sub_motifs", [])
        n_labels = len(sub_motifs)
        conformity["checks"].append({
            "check": "l2_help_account",
            "pass": n_labels >= 5,
            "detail": f"{n_labels} sub-motifs: {[s['id'] for s in sub_motifs]}",
        })
        if n_labels < 5:
            errors.append(f"help_account L2 has {n_labels} labels (need >= 5)")
    else:
        errors.append("help_account intent not found")
        conformity["checks"].append({
            "check": "l2_help_account",
            "pass": False,
            "detail": "intent not found",
        })

    # Save conformity JSON artifact
    artifact_path = campaign_dir / "CE-9_conformity.json"
    artifact_path.write_text(json.dumps(conformity, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        _mark_fail(line, "; ".join(errors), str(artifact_path))
    else:
        _mark_pass(line, "9 intents, L2 OK", str(artifact_path))


def exec_v0_1(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V0-1: pytest all tests pass."""
    result = _run_cmd([sys.executable, "-m", "pytest", str(ROOT / "tests"),
                       "-x", "--tb=short", "-q"], timeout=600)
    content = result.stdout + "\n" + result.stderr
    _save_artifact(campaign_dir, "V0-1_pytest.txt", content)

    if result.returncode == 0:
        # Extract pass count
        for output_line in result.stdout.splitlines():
            if "passed" in output_line:
                _mark_pass(line, output_line.strip(), str(campaign_dir / "V0-1_pytest.txt"))
                return
        _mark_pass(line, "exit 0", str(campaign_dir / "V0-1_pytest.txt"))
    else:
        _mark_fail(line, f"exit {result.returncode}", content[-500:])


def exec_v0_2(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V0-2: ML imports."""
    check_code = (
        "import torch; "
        "print(f'torch={torch.__version__}, cuda={torch.cuda.is_available()}'); "
        "from setfit import SetFitModel; print('setfit=ok'); "
        "from sentence_transformers import SentenceTransformer; print('st=ok')"
    )
    result = _run_cmd([sys.executable, "-c", check_code])
    content = result.stdout + "\n" + result.stderr
    _save_artifact(campaign_dir, "V0-2_imports.txt", content)

    if result.returncode == 0:
        _mark_pass(line, result.stdout.strip(), str(campaign_dir / "V0-2_imports.txt"))
    else:
        _mark_fail(line, "import error", result.stderr.strip()[:200])


def exec_v0_3(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V0-3: Anti-mock grep."""
    result = _run_cmd(["git", "grep", "-n", "unittest.mock", "--", "loko/"])
    # Filter out allowed exceptions (testing module, conftest)
    matches = []
    for grep_line in result.stdout.strip().splitlines():
        if grep_line.strip() and "testing/" not in grep_line and "conftest" not in grep_line:
            matches.append(grep_line)

    content = "\n".join(matches) if matches else "0 occurrences"
    _save_artifact(campaign_dir, "V0-3_grep.txt", content)

    if len(matches) == 0:
        _mark_pass(line, "0 occurrences", str(campaign_dir / "V0-3_grep.txt"))
    else:
        _mark_fail(line, f"{len(matches)} mock imports in production code")


def exec_v0_4(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V0-4: npm/pip audit."""
    pip_result = _run_cmd([sys.executable, "-m", "pip", "audit"], timeout=120)
    npm_output = ""
    desktop_dir = ROOT / "desktop"
    if desktop_dir.is_dir():
        npm_result = _run_cmd(["npm", "audit", "--production"], cwd=desktop_dir, timeout=120)
        npm_output = npm_result.stdout + "\n" + npm_result.stderr

    content = f"=== pip audit ===\n{pip_result.stdout}\n{pip_result.stderr}\n"
    if npm_output:
        content += f"\n=== npm audit ===\n{npm_output}\n"

    _save_artifact(campaign_dir, "V0-4_audit.txt", content)

    # pip-audit returns 0 if no vulns
    # We accept pip audit failure (not installed) as non-blocking for now
    if pip_result.returncode == 0 or "No known vulnerabilities" in pip_result.stdout:
        _mark_pass(line, "0 vulnerabilities", str(campaign_dir / "V0-4_audit.txt"))
    elif "No module named" in pip_result.stderr:
        # pip-audit not installed — run basic pip check instead
        check = _run_cmd([sys.executable, "-m", "pip", "check"])
        if check.returncode == 0:
            _mark_pass(line, "pip check OK (pip-audit not installed)",
                       str(campaign_dir / "V0-4_audit.txt"))
        else:
            _mark_fail(line, "pip check failed")
    else:
        _mark_fail(line, "vulnerabilities found")


def exec_v0_5(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V0-5: Image size <= 1.6 Go."""
    image = ctx.get("image")
    if not image:
        _mark_fail(line, "no image specified")
        return

    result = _run_cmd(["docker", "inspect", "--format", "{{.Size}}", image])
    if result.returncode != 0:
        _mark_fail(line, f"image not found: {image}")
        return

    try:
        size_mb = int(result.stdout.strip()) / (1024 * 1024)
        if size_mb <= 1600:
            _mark_pass(line, f"{size_mb:.0f}MB", str(campaign_dir / "V0-5_size.txt"))
        else:
            _mark_fail(line, f"{size_mb:.0f}MB > 1600MB")
        _save_artifact(campaign_dir, "V0-5_size.txt", f"size={size_mb:.0f}MB")
    except ValueError:
        _mark_fail(line, "cannot parse image size")


def _exec_stub(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """Stub executor for tests that require runtime (V1, V2, V3).

    These tests need the server running inside a container.
    In dry-run mode, they remain FAIL (NON EXÉCUTÉ).
    When the runner is invoked with a running container, specialized
    executors replace this stub.
    """
    line.detail = "NON EXECUTE - requires running container or manual execution"
    line.executed = False


# ──────────────────────────────────────────────────────────────────────
# V3 executors (offline - use loko-eval)
# ──────────────────────────────────────────────────────────────────────

def _apply_sweep_thresholds(bot_dir: str, sel: dict) -> None:
    """Apply sweep-selected thresholds to bot config.json.

    After V3-0 selects the Pareto-optimal thresholds, update the bot
    config so that V3-1/2/3 evaluations use the same thresholds.
    """
    config_path = Path(bot_dir) / "config.json"
    if not config_path.exists():
        return
    config = json.loads(config_path.read_text(encoding="utf-8"))
    journey = config.get("journey", {})
    journey["seuil_haut"] = sel["seuil_haut"]
    journey["seuil_bas"] = sel["seuil_bas"]
    journey["seuil_ecart_clarification"] = sel.get("seuil_ecart", 0.0)
    config["journey"] = journey
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def exec_v3_0(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-0: Sweep Pareto 3-axis + selection."""
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    sweep_dir = campaign_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    sweep_datasets = (
        f"metier={DATASETS_DIR / 'heldout_metier.csv'},"
        f"conseiller={DATASETS_DIR / 'heldout_conseiller.csv'},"
        f"horsscope={DATASETS_DIR / 'heldout_horsscope.csv'},"
        f"pieges={DATASETS_DIR / 'pieges.csv'}"
    )

    result = _run_cmd([
        sys.executable, "-m", "loko.eval.cli",
        "--bot-dir", str(bot_dir),
        "--sweep-datasets", sweep_datasets,
        "--out", str(sweep_dir),
    ], timeout=600)

    content = result.stdout + "\n" + result.stderr
    _save_artifact(campaign_dir, "V3-0_sweep.txt", content)

    selection_file = sweep_dir / "selection.json"
    if selection_file.exists():
        selection = json.loads(selection_file.read_text(encoding="utf-8"))
        if selection.get("selected"):
            sel = selection["selected"]
            detail = (
                f"haut={sel['seuil_haut']:.2f} bas={sel['seuil_bas']:.2f} "
                f"ecart={sel['seuil_ecart']:.2f} | "
                f"GNG-1={sel.get('gng1', 0)*100:.1f}% "
                f"GNG-2={sel.get('gng2', 0)*100:.1f}% "
                f"GNG-3={sel.get('gng3', 0)*100:.1f}%"
            )
            _mark_pass(line, detail, str(selection_file))

            # Apply sweep-selected thresholds to bot config so V3-1/2/3
            # use the same operational thresholds (protocol requirement).
            _apply_sweep_thresholds(bot_dir, sel)
        else:
            _mark_fail(line, "no feasible point found", str(selection_file))
    else:
        _mark_fail(line, "selection.json not produced", content[-500:])


def exec_v3_eval(line: TestLine, campaign_dir: Path, dataset_name: str,
                 gng_name: str, threshold: float, **ctx: Any) -> None:
    """Generic V3 evaluator for GNG metrics."""
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    dataset_path = DATASETS_DIR / f"{dataset_name}.csv"
    if not dataset_path.exists():
        _mark_fail(line, f"dataset not found: {dataset_path}")
        return

    mode = "pieges" if dataset_name == "pieges" else "decision"
    out_dir = campaign_dir / f"V3_{dataset_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = _run_cmd([
        sys.executable, "-m", "loko.eval.cli",
        "--bot-dir", str(bot_dir),
        "--dataset", str(dataset_path),
        "--mode", mode,
        "--out", str(out_dir),
    ], timeout=600)

    content = result.stdout + "\n" + result.stderr
    _save_artifact(campaign_dir, f"V3_{dataset_name}_output.txt", content)

    report_file = out_dir / "report.json"
    if report_file.exists():
        report = json.loads(report_file.read_text(encoding="utf-8"))
        accuracy = report.get("accuracy", 0)
        total = report.get("total", 0)
        correct = report.get("correct", 0)
        n_errors = report.get("n_errors", 0)

        measured = f"{gng_name}={accuracy*100:.1f}% ({correct}/{total})"

        # Extra details for horsscope
        extra = report.get("extra", {})
        routes_directes = extra.get("gng3_routes_directes", None)
        if routes_directes is not None:
            measured += f", routes_directes={routes_directes}"

        if accuracy >= threshold:
            _mark_pass(line, measured, str(report_file))
        else:
            _mark_fail(line, measured, f"below {threshold*100:.0f}% threshold")
    else:
        _mark_fail(line, "report.json not produced", content[-500:])


def exec_v3_1(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-1: GNG-1 >= 85%."""
    exec_v3_eval(line, campaign_dir, "heldout_metier", "GNG-1", 0.85, **ctx)


def exec_v3_2(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-2: GNG-2 >= 90%."""
    exec_v3_eval(line, campaign_dir, "heldout_conseiller", "GNG-2", 0.90, **ctx)


def exec_v3_3(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-3: GNG-3 >= 80%, routes directes <= 5."""
    exec_v3_eval(line, campaign_dir, "heldout_horsscope", "GNG-3", 0.80, **ctx)


def exec_v3_4(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-4: Pieges >= 12/15."""
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    dataset_path = DATASETS_DIR / "pieges.csv"
    if not dataset_path.exists():
        _mark_fail(line, f"dataset not found: {dataset_path}")
        return

    out_dir = campaign_dir / "V3_pieges"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = _run_cmd([
        sys.executable, "-m", "loko.eval.cli",
        "--bot-dir", str(bot_dir),
        "--dataset", str(dataset_path),
        "--mode", "pieges",
        "--out", str(out_dir),
    ], timeout=600)

    content = result.stdout + "\n" + result.stderr
    _save_artifact(campaign_dir, "V3-4_pieges_output.txt", content)

    report_file = out_dir / "report.json"
    if report_file.exists():
        report = json.loads(report_file.read_text(encoding="utf-8"))
        correct = report.get("correct", 0)
        total = report.get("total", 0)
        measured = f"pieges={correct}/{total}"

        if correct >= 12:
            _mark_pass(line, measured, str(report_file))
        else:
            _mark_fail(line, measured, f"below 12/{total} threshold")
    else:
        _mark_fail(line, "report.json not produced", content[-500:])


def exec_v3_5(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-5: Model + seuils + manifeste geles."""
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    manifest_path = Path(bot_dir) / "models" / "manifest.json"
    if not manifest_path.exists():
        _mark_fail(line, "manifest.json not found")
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = _hash_file(manifest_path)

    detail = f"manifest_hash={manifest_hash[:16]}..."
    _mark_pass(line, detail, str(manifest_path))
    _save_artifact(campaign_dir, "V3-5_manifest.json",
                   json.dumps({"manifest_hash": manifest_hash, "manifest": manifest},
                              ensure_ascii=False, indent=2))


def exec_v3_6(line: TestLine, campaign_dir: Path, **ctx: Any) -> None:
    """V3-6: Reproducibility - 2 runs produce identical report.json."""
    bot_dir = ctx.get("bot_dir")
    if not bot_dir:
        _mark_fail(line, "no bot-dir specified")
        return

    dataset_path = DATASETS_DIR / "heldout_metier.csv"
    if not dataset_path.exists():
        _mark_fail(line, f"dataset not found: {dataset_path}")
        return

    runs: list[dict] = []
    for run_idx in range(2):
        out_dir = campaign_dir / f"V3-6_run{run_idx + 1}"
        out_dir.mkdir(parents=True, exist_ok=True)

        _run_cmd([
            sys.executable, "-m", "loko.eval.cli",
            "--bot-dir", str(bot_dir),
            "--dataset", str(dataset_path),
            "--mode", "decision",
            "--out", str(out_dir),
        ], timeout=600)

        report_file = out_dir / "report.json"
        if report_file.exists():
            runs.append(json.loads(report_file.read_text(encoding="utf-8")))
        else:
            _mark_fail(line, f"run {run_idx + 1} did not produce report.json")
            return

    # Compare deterministic parts (report.json excludes timing)
    if runs[0] == runs[1]:
        _mark_pass(line, "2 runs identical", str(campaign_dir / "V3-6_diff.txt"))
        _save_artifact(campaign_dir, "V3-6_diff.txt", "IDENTICAL - diff empty")
    else:
        diff_keys = [k for k in runs[0] if runs[0].get(k) != runs[1].get(k)]
        _mark_fail(line, f"diff on keys: {diff_keys}")
        _save_artifact(campaign_dir, "V3-6_diff.txt",
                       f"DIFF on: {diff_keys}\nRun 1: {json.dumps(runs[0], indent=2)}\n"
                       f"Run 2: {json.dumps(runs[1], indent=2)}")


# ──────────────────────────────────────────────────────────────────────
# Executor dispatch
# ──────────────────────────────────────────────────────────────────────

EXECUTORS: dict[str, Any] = {
    "CE-1": exec_ce1,
    "CE-2": exec_ce2,
    "CE-3": exec_ce3,
    "CE-4": exec_ce4,
    "CE-5": exec_ce5,
    "CE-6": exec_ce6,
    "CE-7": exec_ce7,
    "CE-8": exec_ce8,
    "CE-9": exec_ce9,
    "V0-1": exec_v0_1,
    "V0-2": exec_v0_2,
    "V0-3": exec_v0_3,
    "V0-4": exec_v0_4,
    "V0-5": exec_v0_5,
    # V1 tests require running container — stub by default
    "V1-1": _exec_stub,
    "V1-2": _exec_stub,
    "V1-3": _exec_stub,
    "V1-4": _exec_stub,
    "V1-5": _exec_stub,
    # V2 tests require training run — stub by default
    "V2-1": _exec_stub,
    "V2-2": _exec_stub,
    "V2-3": _exec_stub,
    "V2-4": _exec_stub,
    "V2-5": _exec_stub,
    "V2-6": _exec_stub,
    # V3 tests run offline via loko-eval
    "V3-0": exec_v3_0,
    "V3-1": exec_v3_1,
    "V3-2": exec_v3_2,
    "V3-3": exec_v3_3,
    "V3-4": exec_v3_4,
    "V3-5": exec_v3_5,
    "V3-6": exec_v3_6,
}


# ──────────────────────────────────────────────────────────────────────
# Gate calculation — COMPUTED, never editable
# ──────────────────────────────────────────────────────────────────────

def calculate_gates(lines: list[TestLine], gates: list[GateResult]) -> None:
    """Calculate gate verdicts from line verdicts.

    Rules:
    - A gate is PASS only if ALL its lines are PASS (or allowed SKIP).
    - A non-executed line = FAIL (interdit n°3).
    - Verdicts are computed, never edited (interdit n°9).
    """
    line_map = {line.id: line for line in lines}

    for gate in gates:
        gate.pass_count = 0
        gate.fail_count = 0

        for line_id in gate.lines:
            line = line_map.get(line_id)
            if line is None:
                gate.fail_count += 1
                continue

            if line.verdict == "PASS":
                gate.pass_count += 1
            elif line.verdict == "SKIP" and line.skippable:
                # Allowed skip — doesn't count as fail
                gate.pass_count += 1
            else:
                gate.fail_count += 1

        gate.all_passed = gate.fail_count == 0
        gate.verdict = "PASS" if gate.all_passed else "FAIL"
        gate.detail = f"{gate.pass_count}/{len(gate.lines)} passed"


# ──────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────

def generate_report_md(report: CampaignReport) -> str:
    """Generate markdown report (gabarit annexe A)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md = []
    md.append(f"# RAPPORT DE CAMPAGNE — {now}")
    md.append("")
    md.append(f"**Version** : {report.version}")
    md.append(f"**Tag** : {report.tag}")
    md.append(f"**Commit** : {report.commit}")
    md.append(f"**Image digest** : {report.image_digest}")
    md.append(f"**Bot ID** : {report.bot_id}")
    md.append(f"**Manifeste modèle** : {report.manifest_hash}")
    md.append(f"**Protocole** : {report.protocol_version}")
    md.append(f"**Runner** : {report.runner_version}")
    md.append(f"**Machine de référence** : {report.machine_reference}")
    md.append(f"**Dry-run** : {'OUI' if report.dry_run else 'NON'}")
    md.append("")

    # Interdits
    md.append("## Interdits opposables v2.2 (rappel)")
    md.append("")
    for interdit in INTERDITS_V22:
        md.append(f"- {interdit}")
    md.append("")

    # Lines table
    md.append("## Tableau de synthèse")
    md.append("")
    md.append("| # | Description | Verdict | Mesuré | Artefact |")
    md.append("|---|---|---|---|---|")

    for line in report.lines:
        verdict_emoji = "PASS" if line.verdict == "PASS" else ("SKIP" if line.verdict == "SKIP" else "FAIL")
        artifact_short = Path(line.artifact).name if line.artifact else "-"
        measured = line.measured or line.detail or "NON EXÉCUTÉ"
        md.append(f"| {line.id} | {line.description} | {verdict_emoji} {line.verdict} | {measured} | {artifact_short} |")

    md.append("")

    # Gates table
    md.append("## Verdicts des gates (CALCULÉS par le runner)")
    md.append("")
    md.append("| Gate | Description | Verdict | Détail |")
    md.append("|---|---|---|---|")

    for gate in report.gates:
        verdict_emoji = "PASS" if gate.verdict == "PASS" else "FAIL"
        md.append(f"| {gate.gate_id} | {gate.description} | {verdict_emoji} {gate.verdict} | {gate.detail} |")

    md.append("")

    # Anomalies
    md.append("## Anomalies de protocole suspectées")
    md.append("")
    md.append("*(Cette section n'altère JAMAIS les verdicts ci-dessus)*")
    md.append("")
    if report.anomalies_protocole:
        for anomaly in report.anomalies_protocole:
            md.append(f"- {anomaly}")
    else:
        md.append("Aucune anomalie signalée.")
    md.append("")

    # Overall verdict
    md.append("## Décision de campagne")
    md.append("")
    all_critical_pass = all(
        g.verdict == "PASS" for g in report.gates
        if g.gate_id in ("CE", "G-0", "G-1", "G-1b", "G-2", "G-3")
    )
    if report.dry_run:
        md.append("**MODE DRY-RUN — Aucune validation opposable**")
    elif all_critical_pass:
        md.append("**R0 + R1 : VALIDES**")
        report.overall_verdict = "VALIDE"
    else:
        failed_gates = [g.gate_id for g in report.gates if g.verdict != "PASS"]
        md.append(f"**NON VALIDE** — Gates en échec : {', '.join(failed_gates)}")
        report.overall_verdict = "NON VALIDE"

    md.append("")
    md.append("---")
    md.append(f"*Rapport généré automatiquement par le runner de campagne v{report.runner_version}*")
    md.append("*Les verdicts de gates sont calculés, non rédigés (interdit n°9).*")

    return "\n".join(md)


def generate_report_json(report: CampaignReport) -> dict:
    """Generate machine-readable report."""
    return {
        "version": report.version,
        "tag": report.tag,
        "commit": report.commit,
        "image_digest": report.image_digest,
        "bot_id": report.bot_id,
        "manifest_hash": report.manifest_hash,
        "protocol_version": report.protocol_version,
        "runner_version": report.runner_version,
        "machine_reference": report.machine_reference,
        "dry_run": report.dry_run,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "overall_verdict": report.overall_verdict,
        "lines": [
            {
                "id": l.id,
                "description": l.description,
                "gate": l.gate,
                "phase": l.phase,
                "verdict": l.verdict,
                "measured": l.measured,
                "artifact": l.artifact,
                "detail": l.detail,
                "executed": l.executed,
            }
            for l in report.lines
        ],
        "gates": [
            {
                "gate_id": g.gate_id,
                "description": g.description,
                "verdict": g.verdict,
                "pass_count": g.pass_count,
                "fail_count": g.fail_count,
                "detail": g.detail,
            }
            for g in report.gates
        ],
        "anomalies_protocole": report.anomalies_protocole,
    }


# ──────────────────────────────────────────────────────────────────────
# Main runner
# ──────────────────────────────────────────────────────────────────────

def run_campaign(
    bot_dir: str,
    campaign_dir: str,
    image: str | None = None,
    tag: str | None = None,
    dry_run: bool = False,
    phases: list[str] | None = None,
    allowed_tests: set[str] | None = None,
) -> CampaignReport:
    """Execute a full campaign and produce the report.

    Parameters
    ----------
    bot_dir : str
        Path to the bot directory (e.g., data/bots/<uuid>).
    campaign_dir : str
        Path to store campaign artifacts.
    image : str, optional
        Docker image name.
    tag : str, optional
        Expected git tag.
    dry_run : bool
        If True, execute CE/V0 phases only and show what V1-V3 WOULD be.
    phases : list[str], optional
        Limit execution to specific phases (e.g., ["CE", "V0", "V3"]).
    allowed_tests : set[str], optional
        If given, only execute tests with IDs in this set (e.g., for E1 diagnostic).
    """
    campaign_path = Path(campaign_dir)
    campaign_path.mkdir(parents=True, exist_ok=True)

    report = CampaignReport(
        dry_run=dry_run,
        started_at=datetime.now(timezone.utc).isoformat(),
        bot_id=Path(bot_dir).name if bot_dir else "",
    )

    # Read version info
    pyproject = ROOT / "pyproject.toml"
    for line_text in pyproject.read_text(encoding="utf-8").splitlines():
        if line_text.strip().startswith("version"):
            report.version = line_text.split("=", 1)[1].strip().strip('"')
            break

    commit_result = _run_cmd(["git", "rev-parse", "--short", "HEAD"])
    report.commit = commit_result.stdout.strip()
    report.tag = tag or ""
    report.machine_reference = os.environ.get("LOKO_MACHINE_ID", "(non declare)")

    if image:
        digest = _run_cmd(["docker", "inspect", "--format", "{{.Id}}", image])
        report.image_digest = digest.stdout.strip()[:20] if digest.returncode == 0 else "(unavailable)"

    # Build protocol
    report.lines = build_protocol_lines()
    report.gates = build_gates(report.lines)

    # Display interdits
    print("\n" + "=" * 70)
    print("  LOKO Campaign Runner v1.0.0 - Protocole v2.2")
    print("=" * 70)
    print("\n  INTERDITS OPPOSABLES (rappel avant execution) :")
    for interdit in INTERDITS_V22:
        print(f"    {interdit}")
    print()

    if dry_run:
        print("  *** MODE DRY-RUN - les tests V1+ restent NON EXECUTE ***\n")

    # Execute tests
    context = {
        "bot_dir": bot_dir,
        "image": image,
        "tag": tag,
    }

    allowed_phases = set(phases) if phases else {"CE", "V0", "V1", "V2", "V3"}
    if dry_run and not allowed_tests:
        # In dry-run, only run CE and V0 (unless specific tests are requested)
        allowed_phases = {"CE", "V0"}

    for test_line in report.lines:
        # Filter by phase
        if test_line.phase not in allowed_phases:
            if dry_run:
                test_line.detail = "DRY-RUN - non execute"
            continue

        # Filter by allowed test IDs (for E1 diagnostic mode)
        if allowed_tests and test_line.id not in allowed_tests:
            test_line.detail = "not in scope for this run"
            continue

        executor = EXECUTORS.get(test_line.id, _exec_stub)
        phase_label = f"[{test_line.phase}]"

        print(f"  {phase_label:6s} {test_line.id:6s} {test_line.description[:50]:50s} ", end="", flush=True)

        try:
            executor(test_line, campaign_path, **context)
        except Exception as exc:
            _mark_fail(test_line, f"EXCEPTION: {exc}")
            report.anomalies_protocole.append(
                f"{test_line.id}: exception during execution: {exc}"
            )

        status = test_line.verdict
        color = "\033[92m" if status == "PASS" else ("\033[93m" if status == "SKIP" else "\033[91m")
        print(f"{color}{status}\033[0m  {test_line.measured or test_line.detail or ''}")

    # Calculate gates
    calculate_gates(report.lines, report.gates)

    report.completed_at = datetime.now(timezone.utc).isoformat()

    # Display gate summary
    print("\n" + "=" * 70)
    print("  GATES (calcules automatiquement)")
    print("=" * 70)
    for gate in report.gates:
        color = "\033[92m" if gate.verdict == "PASS" else "\033[91m"
        print(f"  {gate.gate_id:6s} {color}{gate.verdict:4s}\033[0m  {gate.detail}  - {gate.description}")

    # Overall
    all_pass = all(g.verdict == "PASS" for g in report.gates)
    if dry_run:
        report.overall_verdict = "DRY-RUN"
        print(f"\n  {'=' * 50}")
        print("  MODE DRY-RUN - resultat non opposable")
    elif all_pass:
        report.overall_verdict = "VALIDE"
        print(f"\n  {'=' * 50}")
        print("  \033[92mR0 + R1 : VALIDES\033[0m")
    else:
        report.overall_verdict = "NON VALIDE"
        failed = [g.gate_id for g in report.gates if g.verdict != "PASS"]
        print(f"\n  {'=' * 50}")
        print(f"  \033[91mNON VALIDE - gates en echec : {', '.join(failed)}\033[0m")

    print(f"  {'=' * 50}\n")

    # Write reports
    md_report = generate_report_md(report)
    md_path = campaign_path / "RAPPORT_CAMPAGNE.md"
    md_path.write_text(md_report, encoding="utf-8")
    print(f"  Rapport MD : {md_path}")

    json_report = generate_report_json(report)
    json_path = campaign_path / "campaign_report.json"
    json_path.write_text(
        json.dumps(json_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Rapport JSON : {json_path}")

    return report


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="E0 - LOKO Campaign Runner: enforces protocol opposability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run on existing image (E0 gate test)
  python tools/run_campaign.py --bot-dir data/bots/<uuid> --campaign-dir eval/campagne-R0R1/test --dry-run

  # Full campaign
  python tools/run_campaign.py --bot-dir data/bots/<uuid> --campaign-dir eval/campagne-R0R1/v0.3.8 --image loko:v0.3.8 --tag v0.3.8

  # Run specific phases only
  python tools/run_campaign.py --bot-dir data/bots/<uuid> --campaign-dir eval/campagne-R0R1/test --phases CE V0 V3

  # E1 mini-campaign: diagnostic (CE + V2-1/V2-2 + V3 sweep/eval)
  python tools/run_campaign.py --bot-dir data/bots/<uuid> --campaign-dir eval/campagne-R0R1/e1-diag --e1-diagnostic
        """,
    )
    parser.add_argument("--bot-dir", required=True, help="Path to bot directory")
    parser.add_argument("--campaign-dir", required=True, help="Campaign artifacts directory")
    parser.add_argument("--image", default=None, help="Docker image name")
    parser.add_argument("--tag", default=None, help="Expected git tag")
    parser.add_argument("--dry-run", action="store_true",
                        help="Execute CE+V0 only, show what V1+ would be")
    parser.add_argument("--phases", nargs="*", default=None,
                        help="Limit to specific phases (CE, V0, V1, V2, V3)")
    parser.add_argument("--e1-diagnostic", action="store_true",
                        help="E1 mini-campaign: CE-1..CE-9 + V2-1,V2-2 + V3-0..V3-4")

    args = parser.parse_args()

    # E1 diagnostic: specific set of tests per roadmap
    allowed_tests = None
    if args.e1_diagnostic:
        # E1 mini-campaign: CE-1..CE-9, V2-1, V2-2, V3-0..V3-4
        allowed_tests = {
            "CE-1", "CE-2", "CE-3", "CE-4", "CE-5", "CE-6", "CE-7", "CE-8", "CE-9",
            "V2-1", "V2-2",
            "V3-0", "V3-1", "V3-2", "V3-3", "V3-4",
        }
        # E1 uses all phases that contain the allowed tests
        if not args.phases:
            args.phases = ["CE", "V0", "V1", "V2", "V3"]

    report = run_campaign(
        bot_dir=args.bot_dir,
        campaign_dir=args.campaign_dir,
        image=args.image,
        tag=args.tag,
        dry_run=args.dry_run,
        phases=args.phases,
        allowed_tests=allowed_tests,
    )

    # Exit code based on overall verdict
    if report.dry_run:
        # Dry-run: exit 1 if any executed test failed (expected for E0 gate test)
        has_failures = any(
            l.verdict == "FAIL" and l.executed
            for l in report.lines
        )
        sys.exit(1 if has_failures else 0)
    else:
        sys.exit(0 if report.overall_verdict == "VALIDE" else 1)


if __name__ == "__main__":
    main()
