#!/usr/bin/env python3
"""E1/E2 - Train a bot classifier offline (no server required).

Loads bot config from disk, optionally enriches training data from
an enrichment CSV, trains L1+L2 classifiers, writes manifest.

This tool wraps loko.bot.classifier.training.train_bot_classifiers()
for offline use during campaign preparation.

Usage:
    python tools/train_bot_offline.py --bot-dir data/bots/<uuid>
    python tools/train_bot_offline.py --bot-dir data/bots/<uuid> --enrich enrichment.csv
    python tools/train_bot_offline.py --bot-dir data/bots/<uuid> --train-csv train.csv

Exit code:
    0 - training completed, manifest written
    1 - training error
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config(bot_dir: Path) -> dict:
    """Load and return raw config dict from bot directory."""
    config_path = bot_dir / "config.json"
    if not config_path.is_file():
        print(f"Error: config.json not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(config_path.read_text(encoding="utf-8"))


def enrich_config_from_csv(config: dict, csv_path: Path) -> dict:
    """Add enrichment examples to config intents from a CSV file.

    The CSV must have 'text' and 'intent' columns.
    Examples are added to existing intents; unknown intents are skipped.
    """
    intent_map = {i["id"]: i for i in config.get("intents", [])}
    added = defaultdict(int)

    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            intent_id = row["intent"]
            text = row["text"].strip()
            if not text:
                continue
            if intent_id in intent_map:
                if text not in intent_map[intent_id]["examples"]:
                    intent_map[intent_id]["examples"].append(text)
                    added[intent_id] += 1
            else:
                print(f"  Warning: intent '{intent_id}' not in config, skipping: {text[:50]}")

    total = sum(added.values())
    print(f"Enrichment: {total} examples added from {csv_path.name}")
    for intent_id in sorted(added.keys()):
        print(f"  {intent_id}: +{added[intent_id]}")

    return config


def replace_train_data(config: dict, train_csv: Path) -> dict:
    """Replace all training examples in config from a train CSV.

    The CSV must have 'text' and 'intent' columns.
    """
    examples_by_intent: dict[str, list[str]] = defaultdict(list)
    with open(train_csv, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            examples_by_intent[row["intent"]].append(row["text"].strip())

    intent_map = {i["id"]: i for i in config.get("intents", [])}

    for intent_id, examples in examples_by_intent.items():
        if intent_id in intent_map:
            intent_map[intent_id]["examples"] = examples
        else:
            print(f"  Warning: intent '{intent_id}' in CSV but not in config")

    total = sum(len(ex) for ex in examples_by_intent.values())
    print(f"Training data replaced: {total} examples across {len(examples_by_intent)} intents")
    return config


def train(bot_dir: Path, config_dict: dict, skip_eval: bool = False) -> dict:
    """Run the actual training pipeline."""
    # Set LOKO_DATA_DIR so model_store resolves correctly
    data_dir = bot_dir.parent.parent  # data/bots/uuid -> data/
    os.environ["LOKO_DATA_DIR"] = str(data_dir)

    from loko.bot.models import BotConfig
    from loko.bot.classifier.training import train_bot_classifiers

    config = BotConfig.model_validate(config_dict)

    def on_progress(step: str, detail: dict = None):
        detail = detail or {}
        if step == "l1_preparing":
            print("  [L1] Preparing training data...")
        elif step == "l1_training":
            print(f"  [L1] Training: {detail.get('num_samples', '?')} samples, "
                  f"{detail.get('num_classes', '?')} classes")
        elif step == "l1_evaluating":
            print("  [L1] Cross-validation + margin analysis...")
        elif step == "l2_preparing":
            print(f"  [L2] Preparing: {detail.get('intent', '?')}")
        elif step == "l2_training":
            print(f"  [L2] Training: {detail.get('intent', '?')} "
                  f"({detail.get('num_samples', '?')} samples)")
        elif step == "writing_manifest":
            print("  [--] Writing manifest...")
        elif step == "done":
            profile = detail.get("profile", {})
            if profile:
                print(f"  [OK] Training complete: {profile.get('total_s', '?')}s total "
                      f"(L1={profile.get('l1_train_s', '?')}s, "
                      f"eval={profile.get('eval_s', '?')}s, "
                      f"L2={profile.get('l2_train_s', '?')}s)")

    result = train_bot_classifiers(
        config,
        run_evaluation=not skip_eval,
        on_progress=on_progress,
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E1/E2 - Train bot classifier offline (no server required)",
    )
    parser.add_argument("--bot-dir", required=True,
                        help="Path to bot directory (data/bots/<uuid>)")
    parser.add_argument("--enrich", default=None,
                        help="Path to enrichment CSV (adds examples to existing config)")
    parser.add_argument("--train-csv", default=None,
                        help="Path to full training CSV (replaces all examples)")
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip cross-validation (faster, for iteration)")
    parser.add_argument("--save-config", action="store_true",
                        help="Save enriched config back to config.json")
    parser.add_argument("--output", "-o", default=None,
                        help="Write training report JSON to file")

    args = parser.parse_args()

    bot_dir = Path(args.bot_dir)
    if not bot_dir.is_dir():
        print(f"Error: {bot_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load config
    print(f"\n{'=' * 60}")
    print(f"  LOKO Offline Trainer")
    print(f"{'=' * 60}")
    print(f"  Bot: {bot_dir.name}")

    config = load_config(bot_dir)
    n_intents = len(config.get("intents", []))
    n_examples = sum(len(i.get("examples", [])) for i in config.get("intents", []))
    print(f"  Config: {n_intents} intents, {n_examples} examples")

    # Enrich or replace training data
    if args.train_csv:
        config = replace_train_data(config, Path(args.train_csv))
    elif args.enrich:
        config = enrich_config_from_csv(config, Path(args.enrich))

    # Updated counts
    n_examples_new = sum(len(i.get("examples", [])) for i in config.get("intents", []))
    if n_examples_new != n_examples:
        print(f"  Updated: {n_examples} -> {n_examples_new} examples")

    # Save enriched config if requested
    if args.save_config:
        config_path = bot_dir / "config.json"
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Config saved to {config_path}")

    print(f"\n  Training...")
    print(f"  {'=' * 50}")

    t_start = time.perf_counter()

    try:
        result = train(bot_dir, config, skip_eval=args.skip_eval)
    except ImportError as exc:
        print(f"\n  Error: ML dependencies not available: {exc}", file=sys.stderr)
        print(f"  Install with: pip install setfit sentence-transformers", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  Error: Training failed: {exc}", file=sys.stderr)
        sys.exit(1)

    duration = time.perf_counter() - t_start

    # Display results
    print(f"\n  {'=' * 50}")
    print(f"  TRAINING RESULTS")
    print(f"  {'=' * 50}")

    l1 = result.get("level1", {})
    print(f"  L1: {l1.get('num_classes', '?')} classes, "
          f"{l1.get('num_samples', '?')} samples, "
          f"{l1.get('duration_s', '?')}s")

    l2 = result.get("level2", {})
    for intent_id, l2_result in l2.items():
        if "error" in l2_result:
            print(f"  L2 {intent_id}: {l2_result['error']}")
        else:
            print(f"  L2 {intent_id}: {l2_result.get('num_classes', '?')} classes, "
                  f"{l2_result.get('num_samples', '?')} samples")

    evaluation = result.get("evaluation")
    if evaluation:
        print(f"\n  Evaluation:")
        print(f"    Accuracy: {evaluation.get('accuracy', 0):.2%}")
        per_class = evaluation.get("per_class_f1", {})
        for cls in sorted(per_class.keys()):
            print(f"    F1 {cls}: {per_class[cls]:.2%}")

        advice = evaluation.get("advice", [])
        if advice:
            print(f"\n  Advice ({len(advice)} items):")
            for a in advice[:5]:
                print(f"    - [{a.get('severity', '?')}] {a.get('message', '?')}")

    latency = result.get("inference_latency_ms", {})
    if latency:
        print(f"\n  Inference latency:")
        print(f"    P50={latency.get('p50', '?')}ms P95={latency.get('p95', '?')}ms")

    manifest = result.get("manifest", "unknown")
    print(f"\n  Manifest: {manifest}")
    print(f"  Total duration: {duration:.1f}s")

    # Write report
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  Report: {out_path}")

    # Check V2-1 constraint (training time <= 300s)
    profile = result.get("profile", {})
    total_s = profile.get("total_s", duration)
    if total_s > 300:
        print(f"\n  WARNING: Training took {total_s:.0f}s > 300s (V2-1 threshold)")
    else:
        print(f"\n  V2-1 OK: Training time {total_s:.0f}s <= 300s")

    print()


if __name__ == "__main__":
    main()
