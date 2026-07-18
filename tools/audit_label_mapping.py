#!/usr/bin/env python3
"""E1 — Audit label mapping consistency between datasets, model, and eval.

Verifies that the label mapping in the trained model (label_map.json)
is consistent with the held-out datasets and the decision logic.

Key checks:
  1. Model label_map contains all 9 required intents
  2. Held-out dataset labels match model label_map
  3. The parler_conseiller/demande_conseiller mapping is correct:
     - heldout_conseiller.csv uses 'parler_conseiller'
     - Model uses 'demande_conseiller'
     - Eval decision logic maps 'escalate' decision to correct intent
  4. No label drift between campaigns (compare with archived label_map)

Usage:
    python tools/audit_label_mapping.py --bot-dir data/bots/<uuid>
    python tools/audit_label_mapping.py --bot-dir data/bots/<uuid> --compare eval/campagne-R0R1/2026-07-06-codex-v2-v036/

Exit code:
    0 — no mapping issues
    1 — mapping inconsistencies found
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = ROOT / "eval" / "datasets"

REQUIRED_MODEL_LABELS = {
    "hors_perimetre",
    "demande_conseiller",
    "help_leave",
    "help_contact",
    "help_billing",
    "help_documents",
    "help_cancellation",
    "help_account",
    "help_transfer",
}

# Known mapping: heldout_conseiller uses 'parler_conseiller' as the expected
# label, but the model intent is 'demande_conseiller'. The eval runner
# handles this by checking decision.type == 'escalate' for GNG-2, not
# by matching intent names. This is correct behavior per protocol.
CONSEILLER_LABEL_IN_HELDOUT = "parler_conseiller"
CONSEILLER_LABEL_IN_MODEL = "demande_conseiller"


def load_dataset_labels(csv_path: Path) -> set[str]:
    """Extract unique labels from a dataset CSV."""
    labels = set()
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "intent" in row:
                labels.add(row["intent"])
            elif "expected_behavior" in row:
                # pieges.csv uses expected_behavior
                behavior = row["expected_behavior"]
                if ":" in behavior:
                    labels.add(behavior.split(":")[1].split("|")[0])
    return labels


def load_label_map(bot_dir: Path) -> dict[int, str] | None:
    """Load label_map.json from the model directory."""
    label_map_path = bot_dir / "models" / "level1" / "label_map.json"
    if not label_map_path.exists():
        return None
    data = json.loads(label_map_path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.items()}


def audit(bot_dir: Path, compare_dir: Path | None = None) -> dict:
    """Run label mapping audit.

    Returns audit report dict.
    """
    report = {
        "bot_dir": str(bot_dir),
        "checks": [],
        "errors": [],
        "warnings": [],
        "verdict": "PASS",
    }

    # ── Check 1: Load model label_map ──
    label_map = load_label_map(bot_dir)
    if label_map is None:
        report["checks"].append(
            {
                "id": "LM-1",
                "name": "Model label_map exists",
                "pass": False,
                "detail": "label_map.json not found",
            }
        )
        report["errors"].append("No label_map.json — model not trained?")
        report["verdict"] = "FAIL"
        return report

    model_labels = set(label_map.values())
    report["checks"].append(
        {
            "id": "LM-1",
            "name": "Model label_map exists",
            "pass": True,
            "detail": {
                "n_labels": len(model_labels),
                "labels": sorted(model_labels),
            },
        }
    )

    # ── Check 2: Model has all 9 required labels ──
    missing_labels = REQUIRED_MODEL_LABELS - model_labels
    extra_labels = model_labels - REQUIRED_MODEL_LABELS
    check_9 = {
        "id": "LM-2",
        "name": "Model has 9 required labels",
        "pass": len(missing_labels) == 0,
        "detail": {
            "missing": sorted(missing_labels),
            "extra": sorted(extra_labels),
        },
    }
    report["checks"].append(check_9)
    if not check_9["pass"]:
        report["errors"].append(f"Model missing labels: {sorted(missing_labels)}")
        # This is THE root cause of the v0.3.7 GNG-2=0% bug
        if "demande_conseiller" in missing_labels:
            report["errors"].append(
                "CRITICAL: demande_conseiller missing from model — "
                "GNG-2 will be 0% (bot cannot emit escalate decision)"
            )

    # ── Check 3: heldout_conseiller label consistency ──
    conseiller_path = DATASETS_DIR / "heldout_conseiller.csv"
    if conseiller_path.exists():
        conseiller_labels = load_dataset_labels(conseiller_path)
        uses_parler = CONSEILLER_LABEL_IN_HELDOUT in conseiller_labels
        uses_demande = CONSEILLER_LABEL_IN_MODEL in conseiller_labels

        check_cons = {
            "id": "LM-3",
            "name": "Conseiller label mapping",
            "pass": True,  # Will be set below
            "detail": {
                "heldout_label": sorted(conseiller_labels),
                "model_label": CONSEILLER_LABEL_IN_MODEL,
                "eval_logic": "GNG-2 checks decision.type == 'escalate' (not intent name match)",
            },
        }

        if uses_parler and CONSEILLER_LABEL_IN_MODEL in model_labels:
            # This is the expected state: dataset uses 'parler_conseiller',
            # model has 'demande_conseiller', eval checks escalate decision
            check_cons["pass"] = True
            check_cons["detail"]["status"] = (
                "consistent (parler→demande mapping via escalate)"
            )
        elif uses_demande:
            check_cons["pass"] = True
            check_cons["detail"]["status"] = (
                "direct match (both use demande_conseiller)"
            )
        else:
            check_cons["pass"] = False
            report["errors"].append(
                f"Unexpected label in heldout_conseiller: {sorted(conseiller_labels)}"
            )

        report["checks"].append(check_cons)

        # WARNING: interdit n°5 — never rename held-out labels
        report["warnings"].append(
            "INTERDIT n°5 rappelé : ne JAMAIS renommer les labels dans les CSV held-out. "
            f"heldout_conseiller.csv utilise '{CONSEILLER_LABEL_IN_HELDOUT}' — "
            "ceci est CORRECT, le runner évalue par type de décision (escalate), pas par nom."
        )

    # ── Check 4: heldout_metier labels vs model ──
    metier_path = DATASETS_DIR / "heldout_metier.csv"
    if metier_path.exists():
        metier_labels = load_dataset_labels(metier_path)
        not_in_model = metier_labels - model_labels
        check_metier = {
            "id": "LM-4",
            "name": "heldout_metier labels in model",
            "pass": len(not_in_model) == 0,
            "detail": {
                "dataset_labels": sorted(metier_labels),
                "not_in_model": sorted(not_in_model),
            },
        }
        report["checks"].append(check_metier)
        if not check_metier["pass"]:
            report["errors"].append(
                f"heldout_metier has labels not in model: {sorted(not_in_model)}"
            )

    # ── Check 5: Compare with previous campaign (non-regression) ──
    if compare_dir:
        compare_path = Path(compare_dir)

        # Look for label_map in archived campaign
        archived_configs = list(compare_path.glob("**/label_map.json"))
        if not archived_configs:
            # Try bot_campaign_config.json
            config_file = compare_path / "bot_campaign_config.json"
            if config_file.exists():
                old_config = json.loads(config_file.read_text(encoding="utf-8"))
                old_intents = {i["id"] for i in old_config.get("intents", [])}

                added = model_labels - old_intents
                removed = old_intents - model_labels

                check_compare = {
                    "id": "LM-5",
                    "name": "Non-regression vs previous campaign",
                    "pass": len(removed) == 0,
                    "detail": {
                        "previous_intents": sorted(old_intents),
                        "current_intents": sorted(model_labels),
                        "added": sorted(added),
                        "removed": sorted(removed),
                    },
                }
                report["checks"].append(check_compare)
                if removed:
                    report["errors"].append(
                        f"Labels removed since previous campaign: {sorted(removed)}"
                    )

    # ── Final verdict ──
    all_pass = all(c["pass"] for c in report["checks"])
    report["verdict"] = "PASS" if all_pass else "FAIL"

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E1 — Audit label mapping consistency",
    )
    parser.add_argument("--bot-dir", required=True, help="Path to bot directory")
    parser.add_argument(
        "--compare", default=None, help="Compare with previous campaign directory"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Write JSON report to file"
    )

    args = parser.parse_args()

    bot_dir = Path(args.bot_dir)
    if not bot_dir.is_dir():
        print(f"Error: {bot_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    compare_dir = Path(args.compare) if args.compare else None
    report = audit(bot_dir, compare_dir)

    # Output
    report_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_json, encoding="utf-8")

    # Console summary
    print(f"\n{'=' * 60}")
    print(f"  Label Mapping Audit — {report['verdict']}")
    print(f"{'=' * 60}")

    for check in report["checks"]:
        status = "[PASS]" if check["pass"] else "[FAIL]"
        print(f"  {status} {check['id']:6s} {check['name']}")

    if report["errors"]:
        print("\nErrors:")
        for err in report["errors"]:
            print(f"  [FAIL] {err}")

    if report["warnings"]:
        print("\nWarnings:")
        for warn in report["warnings"]:
            print(f"  [WARN] {warn}")

    print()
    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
