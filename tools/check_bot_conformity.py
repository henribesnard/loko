#!/usr/bin/env python3
"""E1 — CE-9 Bot conformity checker (protocol v2.2).

Verifies that a bot config meets the postulat requirements BEFORE V2:
  - 9 intentions (7 métier + hors_perimetre + demande_conseiller)
  - ≥ 8 examples per non-system intent
  - hors_perimetre and demande_conseiller marked is_system=true
  - L2 help_account declared with ≥ 5 sub-motif labels
  - Each sub-motif has ≥ 3 examples

Produces a machine-readable JSON conformity report (CE-9 artifact).

Usage:
    python tools/check_bot_conformity.py <bot_dir>
    python tools/check_bot_conformity.py data/bots/<uuid> --output campaign/CE-9.json

Exit code:
    0 — conformity PASS
    1 — conformity FAIL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_INTENTS = {
    "hors_perimetre", "demande_conseiller",
    "help_leave", "help_contact", "help_billing",
    "help_documents", "help_cancellation", "help_account",
    "help_transfer",
}

SYSTEM_INTENTS = {"hors_perimetre", "demande_conseiller"}

MIN_EXAMPLES_PER_INTENT = 8
MIN_L2_LABELS = 5
MIN_L2_EXAMPLES = 3


def check_conformity(config: dict) -> dict:
    """Run CE-9 conformity checks on a bot config.

    Returns a conformity report dict with:
      - bot_id, n_intents, intent_ids
      - checks: list of individual check results
      - errors: list of error messages
      - verdict: PASS or FAIL
    """
    intents = config.get("intents", [])
    intent_ids = {i["id"] for i in intents}

    report = {
        "check": "CE-9",
        "description": "Bot conformity (protocol v2.2)",
        "bot_id": config.get("bot_id", ""),
        "bot_name": config.get("name", ""),
        "n_intents": len(intents),
        "intent_ids": sorted(intent_ids),
        "checks": [],
        "errors": [],
        "verdict": "PASS",
    }

    # ── Check 1: 9 intents present ──
    missing = REQUIRED_INTENTS - intent_ids
    extra = intent_ids - REQUIRED_INTENTS
    check_9 = {
        "id": "CE-9.1",
        "name": "9 required intents",
        "pass": len(missing) == 0 and len(intents) == 9,
        "detail": {
            "expected": 9,
            "found": len(intents),
            "missing": sorted(missing),
            "extra": sorted(extra),
        },
    }
    report["checks"].append(check_9)
    if not check_9["pass"]:
        if missing:
            report["errors"].append(f"Missing intents: {sorted(missing)}")
        if len(intents) != 9:
            report["errors"].append(f"Expected 9 intents, got {len(intents)}")

    # ── Check 2: ≥ 8 examples per non-system intent ──
    for intent in intents:
        n_ex = len(intent.get("examples", []))
        is_sys = intent.get("is_system", False)
        min_req = 0 if is_sys else MIN_EXAMPLES_PER_INTENT

        check_ex = {
            "id": f"CE-9.2/{intent['id']}",
            "name": f"examples for {intent['id']}",
            "pass": n_ex >= min_req,
            "detail": {
                "examples": n_ex,
                "minimum": min_req,
                "is_system": is_sys,
            },
        }
        report["checks"].append(check_ex)
        if not check_ex["pass"]:
            report["errors"].append(
                f"Intent '{intent['id']}' has {n_ex} examples (min {min_req})"
            )

    # ── Check 3: System flags ──
    for sys_id in SYSTEM_INTENTS:
        intent = next((i for i in intents if i["id"] == sys_id), None)
        if intent:
            is_marked = intent.get("is_system", False)
            check_sys = {
                "id": f"CE-9.3/{sys_id}",
                "name": f"is_system flag for {sys_id}",
                "pass": is_marked,
                "detail": {"is_system": is_marked},
            }
            report["checks"].append(check_sys)
            if not is_marked:
                report["errors"].append(f"Intent '{sys_id}' not marked is_system=true")

    # ── Check 4: L2 help_account ≥ 5 labels ──
    sel = next((i for i in intents if i["id"] == "help_account"), None)
    if sel:
        subs = sel.get("sub_motifs", [])
        sub_ids = [s["id"] for s in subs]

        check_l2 = {
            "id": "CE-9.4",
            "name": "L2 help_account",
            "pass": len(subs) >= MIN_L2_LABELS,
            "detail": {
                "n_labels": len(subs),
                "minimum": MIN_L2_LABELS,
                "label_ids": sub_ids,
            },
        }
        report["checks"].append(check_l2)
        if not check_l2["pass"]:
            report["errors"].append(
                f"help_account L2 has {len(subs)} labels (need ≥ {MIN_L2_LABELS})"
            )

        # ── Check 5: Each sub-motif has ≥ 3 examples ──
        for sub in subs:
            n_sub_ex = len(sub.get("examples", []))
            check_sub = {
                "id": f"CE-9.5/{sub['id']}",
                "name": f"L2 examples for {sub['id']}",
                "pass": n_sub_ex >= MIN_L2_EXAMPLES,
                "detail": {"examples": n_sub_ex, "minimum": MIN_L2_EXAMPLES},
            }
            report["checks"].append(check_sub)
            if not check_sub["pass"]:
                report["errors"].append(
                    f"Sub-motif '{sub['id']}' has {n_sub_ex} examples (min {MIN_L2_EXAMPLES})"
                )
    else:
        report["checks"].append({
            "id": "CE-9.4",
            "name": "L2 help_account",
            "pass": False,
            "detail": {"error": "intent not found"},
        })
        report["errors"].append("help_account intent not found")

    # ── Final verdict ──
    all_pass = all(c["pass"] for c in report["checks"])
    report["verdict"] = "PASS" if all_pass else "FAIL"

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CE-9 Bot conformity checker (protocol v2.2)",
    )
    parser.add_argument("bot_dir", help="Path to bot directory (containing config.json)")
    parser.add_argument("--output", "-o", default=None,
                        help="Write JSON report to file (default: stdout)")

    args = parser.parse_args()

    config_path = Path(args.bot_dir) / "config.json"
    if not config_path.is_file():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    report = check_conformity(config)

    # Output
    report_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_json, encoding="utf-8")
        print(f"CE-9 report written to {out_path}")
    else:
        sys.stdout.buffer.write(report_json.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    # Summary
    n_pass = sum(1 for c in report["checks"] if c["pass"])
    n_total = len(report["checks"])
    verdict = report["verdict"]

    print(f"\nCE-9: {verdict} — {n_pass}/{n_total} checks passed", file=sys.stderr)

    if report["errors"]:
        print("\nErrors:", file=sys.stderr)
        for err in report["errors"]:
            print(f"  - {err}", file=sys.stderr)

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
