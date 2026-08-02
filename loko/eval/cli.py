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

    A3: returns the full SetFitClassifierAdapter (with calibration
    temperature) so that loko-eval measures exactly what the runtime
    executes.
    """
    import os

    bot_id = bot_dir.name
    data_dir = bot_dir.parent.parent  # ~/.loko/bots/bot-id -> ~/.loko
    os.environ.setdefault("LOKO_DATA_DIR", str(data_dir))

    from loko.bot.classifier.loader import load_classifier
    from loko.bot.errors import ComponentUnavailableError

    try:
        return load_classifier(bot_id)
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
    parser.add_argument(
        "--bot-dir", required=True, help="Path to bot directory (~/.loko/bots/my-bot)"
    )
    parser.add_argument(
        "--dataset", default=None, help="Path to evaluation CSV dataset"
    )
    parser.add_argument(
        "--mode", choices=["raw", "decision", "pieges"], default="decision"
    )
    parser.add_argument(
        "--out", default="eval_output", help="Output directory for results"
    )
    parser.add_argument(
        "--threshold-check",
        type=float,
        default=None,
        help="Minimum accuracy to pass (e.g. 0.85). Exit code 1 if below.",
    )
    parser.add_argument(
        "--sweep",
        nargs="?",
        const="seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05",
        help="Run threshold sweep (C3). Optional: custom ranges.",
    )
    parser.add_argument(
        "--sweep-datasets",
        help=(
            "M2: 3-axis sweep across multiple datasets. Format: "
            "metier=path,conseiller=path,horsscope=path,pieges=path. "
            "Implies --sweep with seuil_ecart axis."
        ),
    )
    parser.add_argument(
        "--ecart-min",
        type=float,
        default=0.05,
        help="Minimum seuil_ecart for Pareto feasibility (default 0.05). "
        "Set to 0.0 when calibration makes ecart irrelevant.",
    )
    parser.add_argument(
        "--sweep-4axis",
        action="store_true",
        help="E2: Run 4-axis sweep (seuil_haut x seuil_bas x seuil_ecart x seuil_ood). "
        "Requires --sweep-datasets and an OOD-enabled classifier.",
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

    # Load classifier and config (A3: use full adapter, same as runtime)
    classifier = _load_classifier(bot_dir)
    config = _load_config(bot_dir)

    from loko.eval.runner import (
        evaluate_decision,
        evaluate_pieges,
        evaluate_raw,
        select_best_thresholds_pareto,
        threshold_sweep,
        threshold_sweep_3axis,
        threshold_sweep_4axis,
        write_report,
    )

    # E2: 4-axis sweep (with OOD threshold)
    if args.sweep_4axis and args.sweep_datasets:
        ds_dict: dict[str, Path] = {}
        for part in args.sweep_datasets.split(","):
            label, path_str = part.strip().split("=")
            p = Path(path_str.strip())
            if not p.is_file():
                print(f"Error: dataset '{label}' not found at {p}", file=sys.stderr)
                sys.exit(1)
            ds_dict[label.strip()] = p

        sweep_str = (
            args.sweep
            or "seuil_haut=0.6:0.98:0.02,seuil_bas=0.3:0.85:0.05,seuil_ecart=0.0:0.20:0.10,seuil_ood=0.1:0.6:0.05"
        )
        ranges = _parse_sweep(sweep_str)
        sh_range = ranges.get("seuil_haut", (0.6, 0.98, 0.02))
        sb_range = ranges.get("seuil_bas", (0.3, 0.85, 0.05))
        se_range = ranges.get("seuil_ecart", (0.0, 0.20, 0.10))
        so_range = ranges.get("seuil_ood", (0.1, 0.6, 0.05))

        results = threshold_sweep_4axis(
            classifier,
            ds_dict,
            config,
            sh_range,
            sb_range,
            se_range,
            so_range,
        )

        out_dir.mkdir(parents=True, exist_ok=True)

        sweep_json = out_dir / "sweep_4axis.json"
        sweep_json.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"4-axis sweep (E2): {len(results)} points written to {sweep_json}")
        print(f"Datasets: {', '.join(f'{k}={v}' for k, v in ds_dict.items())}")

        # Filter feasible
        feasible = [
            p
            for p in results
            if p.get("gng3", 0) >= 0.80 and p.get("gng3_routes_directes", 999) <= 5
        ]
        print(
            f"Feasible points (GNG-3>=80%, routes<=5): {len(feasible)}/{len(results)}"
        )

        if feasible:
            best = max(
                feasible,
                key=lambda p: (
                    p.get("gng1", 0),
                    p.get("gng2", 0),
                    p.get("pieges_correct", 0),
                ),
            )
            print(
                f"  Best: haut={best['seuil_haut']:.2f} bas={best['seuil_bas']:.2f} "
                f"ecart={best['seuil_ecart']:.2f} ood={best['seuil_ood']:.3f}"
            )
            print(
                f"    GNG-1={best.get('gng1', 0) * 100:.1f}% GNG-2={best.get('gng2', 0) * 100:.1f}% "
                f"GNG-3={best.get('gng3', 0) * 100:.1f}%"
            )
        return

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
        sweep_str = (
            args.sweep
            or "seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05,seuil_ecart=0.0:0.25:0.05"
        )
        ranges = _parse_sweep(sweep_str)
        sh_range = ranges.get("seuil_haut", (0.6, 0.9, 0.05))
        sb_range = ranges.get("seuil_bas", (0.3, 0.6, 0.05))
        se_range = ranges.get("seuil_ecart", (0.0, 0.25, 0.05))

        results = threshold_sweep_3axis(
            classifier,
            ds_dict,
            config,
            sh_range,
            sb_range,
            se_range,
        )

        # W3.1: Pareto-constrained selection
        grid_bounds = {
            "seuil_haut": (sh_range[0], sh_range[1]),
            "seuil_bas": (sb_range[0], sb_range[1]),
            "seuil_ecart": (se_range[0], se_range[1]),
        }
        selection = select_best_thresholds_pareto(
            results, grid_bounds, ecart_min=args.ecart_min
        )

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
        print("\nPareto selection (v2.1):")
        print(f"  Feasible points: {selection['feasible_count']}/{len(results)}")
        print(f"  Pareto frontier: {len(selection['pareto_frontier'])} points")

        if selection["selected"]:
            sel = selection["selected"]
            print(
                f"  Selected: haut={sel['seuil_haut']:.2f} bas={sel['seuil_bas']:.2f} ecart={sel['seuil_ecart']:.2f}"
            )
            print(
                f"    GNG-1={sel.get('gng1', 0) * 100:.1f}% GNG-2={sel.get('gng2', 0) * 100:.1f}% GNG-3={sel.get('gng3', 0) * 100:.1f}%"
            )
            print(
                f"    Routes directes={sel.get('gng3_routes_directes', 0)} Pieges={sel.get('pieges_correct', 0)}/{sel.get('pieges_total', 0)}"
            )
        else:
            print(
                "  No feasible point found - see selection.json for closest candidates"
            )

        if selection.get("warnings"):
            print("\nWarnings:")
            for w in selection["warnings"]:
                print(f"  - {w}")

        print(f"\nSelection details: {selection_json}")
        return

    # Require --dataset for non-sweep modes
    if not args.dataset:
        print(
            "Error: --dataset is required (unless using --sweep-datasets)",
            file=sys.stderr,
        )
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
            writer = csv.DictWriter(
                f, fieldnames=list(results[0].keys()) if results else []
            )
            writer.writeheader()
            writer.writerows(results)

        print(f"Sweep results written to {sweep_path} ({len(results)} combinations)")
        return

    # W3.4: pass bot_id for manifest reference
    bot_id = config.bot_id if hasattr(config, "bot_id") else None

    if args.mode == "raw":
        report = evaluate_raw(classifier, dataset_path, bot_id=bot_id)
    elif args.mode == "pieges":
        report = evaluate_pieges(classifier, dataset_path, config, bot_id=bot_id)
    else:
        report = evaluate_decision(classifier, dataset_path, config, bot_id=bot_id)

    # Write results
    write_report(report, out_dir)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  loko-eval | mode={report.mode} | dataset={report.dataset}")
    print(f"{'=' * 60}")
    print(f"  Total: {report.total}")
    print(f"  Correct: {report.correct}")
    print(f"  Accuracy: {report.accuracy:.2%}")
    print(f"  Errors: {len(report.errors)}")
    print(f"  Duration: {report.duration_s:.2f}s")
    print(f"{'=' * 60}")

    if report.errors and args.verbose:
        print("\nTop errors:")
        for e in report.errors[:10]:
            print(f"  [{e.expected}->{e.predicted}] ({e.decision_type}) {e.text[:60]}")

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
            print(
                f"\nOK: accuracy {report.accuracy:.2%} >= threshold {args.threshold_check:.2%}"
            )


if __name__ == "__main__":
    main()
