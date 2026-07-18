#!/usr/bin/env python3
"""D1 — Diff de preuve du re-figeage.

Compares the frozen eval datasets against the original dataset.csv
to show exactly which texts were scrubbed and how.

Usage:
    python tools/diff_refigeage.py
    python tools/diff_refigeage.py --source dataset.csv --datasets eval/datasets/
    python tools/diff_refigeage.py --summary-only
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mirror the scrub pattern from make_datasets.py
_CLIENT_RE = re.compile("m" + "gen", re.IGNORECASE)


def scrub_current(text: str) -> str:
    """Apply the current scrub (v1: brand -> mutuelle)."""
    text = _CLIENT_RE.sub("mutuelle", text)
    text = re.sub(r"\bmutuelle(\s+mutuelle)+\b", "mutuelle", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def load_source(path: Path) -> dict[str, list[dict[str, str]]]:
    """Load dataset.csv and group by original text (lowered)."""
    rows: dict[str, list[dict[str, str]]] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            text_orig = row["text"].strip()
            key = text_orig.lower()
            if key not in rows:
                rows[key] = []
            rows[key].append({
                "text_orig": text_orig,
                "intent_orig": row["intent"].strip(),
            })
    return rows


def load_frozen(path: Path) -> list[dict[str, str]]:
    """Load a frozen CSV (text, intent/expected/expected_behavior)."""
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


def find_scrub_diffs(
    source_index: dict[str, list[dict[str, str]]],
    frozen_rows: list[dict[str, str]],
    dataset_name: str,
) -> list[dict[str, str]]:
    """Find texts where scrub changed something."""
    diffs = []
    for row in frozen_rows:
        frozen_text = row.get("text", "")
        scrubbed_lower = frozen_text.strip().lower()

        # Try to find the original text that would produce this scrubbed text
        found = False
        for orig_key, orig_entries in source_index.items():
            if scrub_current(orig_key) == scrubbed_lower:
                if orig_key != scrubbed_lower:
                    diffs.append({
                        "dataset": dataset_name,
                        "original": orig_entries[0]["text_orig"],
                        "scrubbed": frozen_text.strip(),
                        "intent_orig": orig_entries[0]["intent_orig"],
                        "intent_frozen": row.get("intent", row.get("expected", "")),
                    })
                found = True
                break

        if not found and _CLIENT_RE.search(frozen_text):
            diffs.append({
                "dataset": dataset_name,
                "original": "(not found in source)",
                "scrubbed": frozen_text.strip(),
                "intent_orig": "?",
                "intent_frozen": row.get("intent", row.get("expected", "")),
            })

    return diffs


def count_mutuelle(frozen_rows: list[dict[str, str]]) -> int:
    """Count rows containing 'mutuelle' in text."""
    return sum(
        1 for row in frozen_rows
        if re.search(r"\bmutuelle\b", row.get("text", ""), re.IGNORECASE)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="D1 — Diff de preuve du re-figeage"
    )
    parser.add_argument(
        "--source", default=str(ROOT / "dataset.csv"),
        help="Path to original dataset.csv",
    )
    parser.add_argument(
        "--datasets", default=str(ROOT / "eval" / "datasets"),
        help="Path to frozen datasets directory",
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Only show summary counts, not individual diffs",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    datasets_dir = Path(args.datasets)

    if not source_path.is_file():
        print(f"Error: {source_path} not found", file=sys.stderr)
        sys.exit(1)

    # Load source
    source_index = load_source(source_path)
    print(f"Source: {source_path} ({len(source_index)} unique texts)")

    # Process each frozen dataset
    frozen_files = [
        "train.csv",
        "heldout_metier.csv",
        "heldout_conseiller.csv",
        "heldout_horsscope.csv",
    ]

    total_diffs = 0
    total_mutuelle = 0

    for fname in frozen_files:
        fpath = datasets_dir / fname
        if not fpath.is_file():
            print(f"  SKIP: {fname} not found")
            continue

        frozen = load_frozen(fpath)
        diffs = find_scrub_diffs(source_index, frozen, fname)
        n_mut = count_mutuelle(frozen)
        total_diffs += len(diffs)
        total_mutuelle += n_mut

        print(f"\n--- {fname} ({len(frozen)} rows) ---")
        print(f"  Scrub modifications: {len(diffs)}")
        print(f"  Rows containing 'mutuelle': {n_mut}")

        if not args.summary_only and diffs:
            for d in diffs:
                print(f"    [{d['intent_orig']}] \"{d['original']}\"")
                print(f"      -> \"{d['scrubbed']}\"")

    # Pieges (special format)
    pieges_path = datasets_dir / "pieges.csv"
    if pieges_path.is_file():
        pieges = load_frozen(pieges_path)
        n_mut_pieges = sum(
            1 for row in pieges
            if re.search(r"\bmutuelle\b", row.get("text", ""), re.IGNORECASE)
        )
        total_mutuelle += n_mut_pieges
        print(f"\n--- pieges.csv ({len(pieges)} rows) ---")
        print(f"  Rows containing 'mutuelle': {n_mut_pieges}")
        if not args.summary_only and n_mut_pieges:
            for row in pieges:
                if re.search(r"\bmutuelle\b", row.get("text", ""), re.IGNORECASE):
                    print(f"    [{row.get('id', '?')}] \"{row['text']}\"")

    print(f"\n=== Summary ===")
    print(f"  Total scrub modifications: {total_diffs}")
    print(f"  Total rows with 'mutuelle': {total_mutuelle}")
    print(f"  Impact: 'mutuelle' is a common French word that reduces discriminative")
    print(f"  power for the classifier, especially for parler_conseiller in GNG-2.")


if __name__ == "__main__":
    main()
