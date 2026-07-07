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
    """Load the trained SetFit classifier from a bot directory.

    Sets LOKO_DATA_DIR so model_store resolves the correct path,
    then delegates to the shared loader (C8).
    """
    import os

    bot_id = bot_dir.name
    data_dir = bot_dir.parent.parent  # ~/.loko/bots/bot-id -> ~/.loko
    os.environ.setdefault("LOKO_DATA_DIR", str(data_dir))

    from loko.bot.classifier.loader import load_classifier
    from loko.bot.errors import ComponentUnavailableError

    try:
        adapter = load_classifier(bot_id)
        return adapter._l1  # unwrap adapter — CLI wraps with its own _ClassifierAdapter
    except ComponentUnavailableError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


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
    parser.add_argument("--dataset", default=None, help="Path to evaluation CSV dataset")
    parser.add_argument("--mode", choices=["raw", "decision", "pieges"], default="decision")
    parser.add_argument("--out", default="eval_output", help="Output directory for results")
    parser.add_argument("--threshold-check", type=float, default=None,
                        help="Minimum accuracy to pass (e.g. 0.85). Exit code 1 if below.")
    parser.add_argument("--sweep", nargs="?", const="seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05",
                        help="Run threshold sweep (C3). Optional: custom ranges.")
    parser.add_argument(
        "--sweep-datasets",
        help=(
            "M2: 3-axis sweep across multiple datasets. Format: "
            "metier=path,conseiller=path,horsscope=path,pieges=path. "
            "Implies --sweep with seuil_ecart axis."
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    bot_dir = Path(args.bot_dir)
    out_dir = Path(args.out)

    if not bot_dir.is_dir():
        print(f"Error: {bot_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load classifier and config
    raw_clf = _load_classifier(bot_dir)
    classifier = _ClassifierAdapter(raw_clf)
    config = _load_config(bot_dir)

    from loko.eval.runner import (
        evaluate_decision,
        evaluate_pieges,
        evaluate_raw,
        select_best_thresholds_pareto,
        threshold_sweep,
        threshold_sweep_3axis,
        write_report,
    )

    # M2: 3-axis sweep across multiple datasets
    if args.sweep_datasets:
        ds_dict: dict[str, Path] = {}
        for part in args.sweep_datasets.split(","):
            label, path_str = part.strip().split("=")
            p = Path(path_str.strip())
            if not p.is_file():
                print(f"Error: dataset '{label}' not found at {p}", file=sys.stderr)
                sys.exit(1)
            ds_dict[label.strip()] = p

        # Parse sweep ranges (including seuil_ecart)
        sweep_str = args.sweep or "seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05,seuil_ecart=0.0:0.25:0.05"
        ranges = _parse_sweep(sweep_str)
        sh_range = ranges.get("seuil_haut", (0.6, 0.9, 0.05))
        sb_range = ranges.get("seuil_bas", (0.3, 0.6, 0.05))
        se_range = ranges.get("seuil_ecart", (0.0, 0.25, 0.05))

        results = threshold_sweep_3axis(
            classifier, ds_dict, config, sh_range, sb_range, se_range,
        )

        # W3.1: Pareto-constrained selection
        grid_bounds = {
            "seuil_haut": (sh_range[0], sh_range[1]),
            "seuil_bas": (sb_range[0], sb_range[1]),
            "seuil_ecart": (se_range[0], se_range[1]),
        }
        selection = select_best_thresholds_pareto(results, grid_bounds)

        out_dir.mkdir(parents=True, exist_ok=True)

        # Write full sweep results (with pareto markers)
        sweep_path = out_dir / "sweep_3axis.csv"
        if results:
            with open(sweep_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
                writer.writeheader()
                writer.writerows(results)

        # Also write as JSON for programmatic use
        sweep_json = out_dir / "sweep_3axis.json"
        sweep_json.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Write selection result
        selection_json = out_dir / "selection.json"
        selection_json.write_text(
            json.dumps(selection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Report selection
        print(f"3-axis sweep: {len(results)} points written to {sweep_path}")
        print(f"Datasets: {', '.join(f'{k}={v}' for k, v in ds_dict.items())}")
        print(f"\nPareto selection (v2.1):")
        print(f"  Feasible points: {selection['feasible_count']}/{len(results)}")
        print(f"  Pareto frontier: {len(selection['pareto_frontier'])} points")

        if selection["selected"]:
            sel = selection["selected"]
            print(f"  Selected: haut={sel['seuil_haut']:.2f} bas={sel['seuil_bas']:.2f} ecart={sel['seuil_ecart']:.2f}")
            print(f"    GNG-1={sel.get('gng1', 0)*100:.1f}% GNG-2={sel.get('gng2', 0)*100:.1f}% GNG-3={sel.get('gng3', 0)*100:.1f}%")
            print(f"    Routes directes={sel.get('gng3_routes_directes', 0)} Pieges={sel.get('pieges_correct', 0)}/{sel.get('pieges_total', 0)}")
        else:
            print("  No feasible point found - see selection.json for closest candidates")

        if selection.get("warnings"):
            print(f"\nWarnings:")
            for w in selection["warnings"]:
                print(f"  - {w}")

        print(f"\nSelection details: {selection_json}")
        return

    # Require --dataset for non-sweep modes
    if not args.dataset:
        print("Error: --dataset is required (unless using --sweep-datasets)", file=sys.stderr)
        sys.exit(1)

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        print(f"Error: {dataset_path} not found", file=sys.stderr)
        sys.exit(1)

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
