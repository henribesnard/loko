#!/usr/bin/env python3
"""C10 — Preflight check for validation campaigns.

Automates CE-1 through CE-7 from the validation protocol.
Run this before declaring a campaign open.

Usage:
    python tools/preflight.py [--tag TAG] [--image IMAGE] [--campaign-dir DIR]

Exit code:
    0 — all checks passed
    1 — one or more checks failed
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = ROOT / "eval" / "datasets"

EXPECTED_FILES = [
    "train.csv",
    "heldout_metier.csv",
    "heldout_conseiller.csv",
    "heldout_horsscope.csv",
    "pieges.csv",
]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _print_result(ce_id: str, description: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    line = f"  {ce_id}  {status:4s}  {description}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return passed


def check_ce1_git_clean() -> bool:
    """CE-1: worktree clean, on main branch."""
    result = _run(["git", "status", "--porcelain"], cwd=ROOT)
    all_lines = [line for line in result.stdout.strip().splitlines() if line.strip()]

    # Separate campaign docs (PLAN_, RAPPORT_, etc.) from real unclean files
    doc_patterns = ("?? PLAN_", "?? PROTOCOLE_", "?? RAPPORT_", "?? AMELIORATION_",
                    " M PLAN_", " M PROTOCOLE_", " M RAPPORT_", " M AMELIORATION_")
    untracked = [line for line in all_lines
                 if not any(line.strip().startswith(p.strip()) for p in doc_patterns)]
    doc_files = [line for line in all_lines if line not in untracked]

    clean = len(untracked) == 0

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT)
    branch_name = branch.stdout.strip()

    passed = clean and branch_name == "main"

    detail = f"branch={branch_name}, untracked={len(untracked)}"
    if not passed and untracked:
        detail += "\n    Non-clean files (action required — commit or move):"
        for line in untracked:
            detail += f"\n      {line.strip()}"
    if doc_files:
        detail += f"\n    Campaign docs (ignored): {len(doc_files)} file(s)"

    return _print_result("CE-1", "Worktree clean, main branch", passed, detail)


def _read_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    pyproject = ROOT / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            # version = "0.3.6"
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "(unknown)"


def check_ce2_tag(tag: str | None, image: str | None = None) -> bool:
    """CE-2: tag present + triple version check (M3).

    Verifies: git describe --tags == pyproject.toml version == pip show loko (in image).
    """
    result = _run(["git", "describe", "--tags", "--exact-match"], cwd=ROOT)
    current_tag = result.stdout.strip()
    if tag:
        ok = current_tag == tag
    else:
        ok = bool(current_tag)
        tag = current_tag or "(none)"

    tag_passed = _print_result("CE-2a", "Tag present", ok, f"tag={tag}")

    # Triple version check (M3)
    pyproject_version = _read_pyproject_version()
    # Strip leading 'v' from tag for comparison (v0.3.6 -> 0.3.6)
    tag_version = current_tag.lstrip("v") if current_tag else "(none)"

    versions_match = tag_version == pyproject_version
    detail = f"tag={tag_version}, pyproject={pyproject_version}"

    # Check pip show loko in image if available
    if image:
        pip_result = _run(["docker", "run", "--rm", image, "pip", "show", "loko"])
        pip_version = "(unknown)"
        if pip_result.returncode == 0:
            for line in pip_result.stdout.splitlines():
                if line.startswith("Version:"):
                    pip_version = line.split(":", 1)[1].strip()
                    break
        versions_match = versions_match and (pip_version == pyproject_version)
        detail += f", pip={pip_version}"
    else:
        detail += ", pip=skipped (no image)"

    triple_passed = _print_result("CE-2b", "Triple version check (M3)", versions_match, detail)

    return tag_passed and triple_passed


def check_ce3_image(image: str | None) -> bool:
    """CE-3: Docker image built from tag, size by digest ≤ 1.6 Go (L6/K4.3)."""
    if not image:
        return _print_result("CE-3", "Docker image built", False, "no --image specified, skipped")

    result = _run(["docker", "inspect", "--format", "{{.Id}}", image])
    if result.returncode != 0:
        return _print_result("CE-3", "Docker image built", False, "image not found")

    digest = result.stdout.strip()[:20]

    # L6: measure size via inspect (not 'docker images') — actual on-disk size
    size_result = _run(["docker", "inspect", "--format", "{{.Size}}", image])
    if size_result.returncode == 0:
        try:
            size_bytes = int(size_result.stdout.strip())
            size_mb = size_bytes / (1024 * 1024)
            threshold_mb = 1600  # 1.6 Go
            size_ok = size_mb <= threshold_mb
            detail = f"image={image}, id={digest}..., size={size_mb:.0f}MB (inspect/digest)"
            if not size_ok:
                detail += f" > {threshold_mb}MB THRESHOLD"
            return _print_result("CE-3", "Docker image built + size", size_ok, detail)
        except ValueError:
            pass

    return _print_result("CE-3", "Docker image built", True, f"image={image}, id={digest}...")


def check_ce4_datasets() -> bool:
    """CE-4: frozen datasets present, hashes match."""
    hashes_file = DATASETS_DIR / "HASHES.sha256"
    if not hashes_file.exists():
        return _print_result("CE-4", "Datasets present + hashes", False, "HASHES.sha256 missing")

    errors: list[str] = []
    for line in hashes_file.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        expected_hash, fname = line.strip().split("  ", 1)
        fpath = DATASETS_DIR / fname
        if not fpath.exists():
            errors.append(f"{fname} missing")
            continue
        actual_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append(f"{fname} hash mismatch")

    for f in EXPECTED_FILES:
        if not (DATASETS_DIR / f).exists():
            errors.append(f"{f} missing")

    ok = len(errors) == 0
    detail = ", ".join(errors) if errors else f"{len(EXPECTED_FILES)} files verified"
    return _print_result("CE-4", "Datasets present + hashes", ok, detail)


def check_ce5_datasets_check() -> bool:
    """CE-5: make_datasets.py --check passes."""
    script = ROOT / "tools" / "make_datasets.py"
    if not script.exists():
        return _print_result("CE-5", "Dataset intersection check", False, "make_datasets.py not found")

    result = _run([sys.executable, str(script), "--check", str(DATASETS_DIR)], cwd=ROOT)
    ok = result.returncode == 0
    detail = "exit 0" if ok else result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"

    return _print_result("CE-5", "Dataset intersection check", ok, detail)


def check_ce6_eval_installed(image: str | None) -> bool:
    """CE-6: loko-eval is importable."""
    # Check locally first (always)
    result = _run([sys.executable, "-c", "from loko.eval.cli import main; print('ok')"])
    local_ok = result.returncode == 0

    if image:
        result = _run(["docker", "run", "--rm", image, "loko-eval", "--help"])
        docker_ok = result.returncode == 0
        ok = local_ok and docker_ok
        detail = f"local={'ok' if local_ok else 'fail'}, docker={'ok' if docker_ok else 'fail'}"
    else:
        ok = local_ok
        detail = f"local={'ok' if local_ok else 'fail'}, docker=skipped"

    return _print_result("CE-6", "loko-eval installed", ok, detail)


def check_ce7_campaign_dir(campaign_dir: str | None) -> bool:
    """CE-7: campaign artifacts directory exists."""
    if not campaign_dir:
        return _print_result("CE-7", "Campaign directory ready", False, "no --campaign-dir specified")

    d = Path(campaign_dir)
    ok = d.is_dir()
    detail = str(d) if ok else f"{d} not found"

    return _print_result("CE-7", "Campaign directory ready", ok, detail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight check for LOKO validation campaigns (C10)")
    parser.add_argument("--tag", default=None, help="Expected git tag (e.g. v0.3.1)")
    parser.add_argument("--image", default=None, help="Docker image to verify (e.g. loko:v0.3.1)")
    parser.add_argument("--campaign-dir", default=None, help="Campaign artifacts directory")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  LOKO Preflight — CE-1 to CE-7")
    print(f"{'='*60}\n")

    results = [
        check_ce1_git_clean(),
        check_ce2_tag(args.tag, args.image),
        check_ce3_image(args.image),
        check_ce4_datasets(),
        check_ce5_datasets_check(),
        check_ce6_eval_installed(args.image),
        check_ce7_campaign_dir(args.campaign_dir),
    ]

    passed = sum(results)
    total = len(results)
    all_ok = all(results)

    print(f"\n{'='*60}")
    print(f"  Result: {passed}/{total} checks passed {'— ALL CLEAR' if all_ok else '— BLOCKED'}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
