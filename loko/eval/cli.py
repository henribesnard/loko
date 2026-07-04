"""C2 — loko-eval CLI entry point.

Usage:
    loko-eval --bot-dir ~/.loko/bots/my-bot --dataset eval/datasets/heldout_metier.csv --mode decision
    loko-eval --bot-dir ~/.loko/bots/my-bot --dataset eval/datasets/pieges.csv --mode pieges
    loko-eval --bot-dir ~/.loko/bots/my-bot --dataset eval/datasets/train.csv --mode raw
    loko-eval --bot-dir ~/.loko/bots/my-bot --dataset eval/datasets/heldout_metier.csv --sweep

Return codes:
    0: all threshold checks pass (or no checks specified)
    1: one or more threshold checks failed
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("loko.eval")


def _load_classifier(bot_dir: Path) -> Any:
    """Load the trained SetFit classifier from a bot directory."""
    from loko.bot.classifier.setfit_service import SetFitClassifier

    bot_id = bot_dir.name
    model_dir = bot_dir / "models" / "level1"

    if not (model_dir / "config.json").exists():
        print(f"Error: No trained model found at {model_dir}", file=sys.stderr)
        sys.exit(1)

    # We need to set LOKO_DATA_DIR so model_store finds the right path
    import os
    data_dir = bot_dir.parent.parent  # ~/.loko/bots/bot-id -> ~/.loko
    os.environ.setdefault("LOKO_DATA_DIR", str(data_dir))

    clf = SetFitClassifier(bot_id, "level1")
    if not clf.load():
        print(f"Error: Failed to load classifier from {model_dir}", file=sys.stderr)
        sys.exit(1)

    return clf


def _load_config(bot_dir: Path) -> Any:
    """Load the bot config from a bot directory."""
    config_path = bot_dir / "config.json"
    if not config_path.is_file():
        print(f"Error: No config found at {config_path}", file=sys.stderr)
        sys.exit(1)

    from loko.bot.models import BotConfig
    return BotConfig.model_validate_json(config_path.read_text(encoding="utf-8"))


class _ClassifierAdapter:
    """Adapt SetFitClassifier to ClassifierProtocol for evaluation."""

    def __init__(self, clf: Any):
        self._clf = clf

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return self._clf.classify(text)


def _parse_sweep(sweep_str: str) -> dict[str, tuple[float, float, float]]:
    """Parse --sweep 'seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05'."""
    result: dict[str, tuple[float, float, float]] = {}
    for part in sweep_str.split(","):
        name, values = part.strip().split("=")
        start, end, step = values.split(":")
        result[name.strip()] = (float(start), float(end), float(step))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LOKO Evaluation CLI (C2) — evaluate classifier + decision logic",
    )
    parser.add_argument("--bot-dir", required=True, help="Path to bot directory (~/.loko/bots/my-bot)")
    parser.add_argument("--dataset", required=True, help="Path to evaluation CSV dataset")
    parser.add_argument("--mode", choices=["raw", "decision", "pieges"], default="decision")
    parser.add_argument("--out", default="eval_output", help="Output directory for results")
    parser.add_argument("--threshold-check", type=float, default=None,
                        help="Minimum accuracy to pass (e.g. 0.85). Exit code 1 if below.")
    parser.add_argument("--sweep", nargs="?", const="seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05",
                        help="Run threshold sweep (C3). Optional: custom ranges.")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    bot_dir = Path(args.bot_dir)
    dataset_path = Path(args.dataset)
    out_dir = Path(args.out)

    if not bot_dir.is_dir():
        print(f"Error: {bot_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not dataset_path.is_file():
        print(f"Error: {dataset_path} not found", file=sys.stderr)
        sys.exit(1)

    # Load classifier and config
    raw_clf = _load_classifier(bot_dir)
    classifier = _ClassifierAdapter(raw_clf)
    config = _load_config(bot_dir)

    from loko.eval.runner import (
        evaluate_decision,
        evaluate_pieges,
        evaluate_raw,
        threshold_sweep,
        write_report,
    )

    # Run evaluation
    if args.sweep:
        ranges = _parse_sweep(args.sweep)
        sh_range = ranges.get("seuil_haut", (0.6, 0.9, 0.05))
        sb_range = ranges.get("seuil_bas", (0.3, 0.6, 0.05))

        results = threshold_sweep(classifier, dataset_path, config, sh_range, sb_range)

        out_dir.mkdir(parents=True, exist_ok=True)
        sweep_path = out_dir / "sweep_results.csv"
        with open(sweep_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else [])
            writer.writeheader()
            writer.writerows(results)

        print(f"Sweep results written to {sweep_path} ({len(results)} combinations)")
        return

    if args.mode == "raw":
        report = evaluate_raw(classifier, dataset_path)
    elif args.mode == "pieges":
        report = evaluate_pieges(classifier, dataset_path, config)
    else:
        report = evaluate_decision(classifier, dataset_path, config)

    # Write results
    write_report(report, out_dir)

    # Summary
    print(f"\n{'='*60}")
    print(f"  loko-eval | mode={report.mode} | dataset={report.dataset}")
    print(f"{'='*60}")
    print(f"  Total: {report.total}")
    print(f"  Correct: {report.correct}")
    print(f"  Accuracy: {report.accuracy:.2%}")
    print(f"  Errors: {len(report.errors)}")
    print(f"  Duration: {report.duration_s:.2f}s")
    print(f"{'='*60}")

    if report.errors and args.verbose:
        print("\nTop errors:")
        for e in report.errors[:10]:
            print(f"  [{e.expected}→{e.predicted}] ({e.decision_type}) {e.text[:60]}")

    print(f"\nResults written to {out_dir}/")

    # Threshold check
    if args.threshold_check is not None:
        if report.accuracy < args.threshold_check:
            print(
                f"\nFAILED: accuracy {report.accuracy:.2%} < threshold {args.threshold_check:.2%}",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(f"\nOK: accuracy {report.accuracy:.2%} >= threshold {args.threshold_check:.2%}")


if __name__ == "__main__":
    main()
