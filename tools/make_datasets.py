#!/usr/bin/env python3
"""C1 — Generate frozen evaluation datasets from MGEN verbatims.

Usage:
    python tools/make_datasets.py --source dataset.csv --out eval/datasets/

Inputs:
    dataset.csv — 6062 MGEN verbatims with columns: text, intent, locale

Outputs (in --out directory):
    train.csv              — postulat examples (from bot config intents)
    heldout_metier.csv     — 100 stratified verbatims from 7 retained intents
    heldout_conseiller.csv — 126 "parler_conseiller" verbatims
    heldout_horsscope.csv  — 100 stratified from 32 non-selected intents
    pieges.csv             — 15 edge cases T01-T15 with expected_behavior
    HASHES.sha256          — deterministic hashes of all generated files

Deterministic: seed=42, all operations sorted before sampling.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# The 7 intents retained in the postulat (from e2e_intents.json)
RETAINED_INTENTS = {
    "services_en_ligne",
    "justificatif_droits",
    "arret_travail",
    "cotisations",
    "changement_coordonnees",
    "teletransmission_noemie",
    "resiliation",
}

# System intent for transverse escalation
CONSEILLER_INTENT = "parler_conseiller"

# Edge cases for trap testing (T01-T15)
PIEGE_CASES = [
    {"id": "T01", "text": "connaitre le montant de ma cotisation et changer mon adresse",
     "expected_behavior": "clarify_inter", "note": "double intention cotisations+changement_coordonnees"},
    {"id": "T02", "text": "bonjour",
     "expected_behavior": "reject", "note": "salutation sans demande"},
    {"id": "T03", "text": "oui",
     "expected_behavior": "reject", "note": "monosyllabe sans contexte"},
    {"id": "T04", "text": "je veux parler a un conseiller pour ma cotisation",
     "expected_behavior": "escalate", "note": "demande_conseiller malgre sujet metier"},
    {"id": "T05", "text": "aide pour rembourser une prothese dentaire",
     "expected_behavior": "reject", "note": "hors scope — dentaire non retenu"},
    {"id": "T06", "text": "comment acceder a mon espace MGEN pour voir mes cotisations",
     "expected_behavior": "clarify_inter", "note": "ambiguite services_en_ligne vs cotisations"},
    {"id": "T07", "text": "j'ai demenage et je dois changer mon RIB et resilier ma mutuelle",
     "expected_behavior": "clarify_inter", "note": "triple intention"},
    {"id": "T08", "text": "aeioiu qlmskd jfqsd",
     "expected_behavior": "reject", "note": "charabia"},
    {"id": "T09", "text": "attestation",
     "expected_behavior": "route", "note": "mot-clé fort — justificatif_droits"},
    {"id": "T10", "text": "noemie",
     "expected_behavior": "route", "note": "mot-clé fort — teletransmission_noemie"},
    {"id": "T11", "text": "comment savoir si mon lien noemie est actif pour etre rembourse",
     "expected_behavior": "route", "note": "teletransmission avec contexte remboursement"},
    {"id": "T12", "text": "je suis en arret depuis 3 mois, quand vais-je etre paye",
     "expected_behavior": "route", "note": "arret_travail formulation indirecte"},
    {"id": "T13", "text": "transferez-moi maintenant",
     "expected_behavior": "escalate", "note": "demande_conseiller implicite aggressive"},
    {"id": "T14", "text": "je ne veux plus etre chez vous, comment faire",
     "expected_behavior": "route", "note": "resiliation formulation indirecte"},
    {"id": "T15", "text": "changement coordonnees bancaires et postales",
     "expected_behavior": "route", "note": "changement_coordonnees — pas d'ambiguite"},
]


def load_source_dataset(path: Path) -> list[dict[str, str]]:
    """Load dataset.csv (text, intent, locale)."""
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"text": row["text"].strip(), "intent": row["intent"].strip()})
    return rows


def stratified_sample(
    rows: list[dict[str, str]],
    n: int,
    rng: random.Random,
) -> list[dict[str, str]]:
    """Sample *n* rows with proportional stratification by intent."""
    by_intent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_intent[row["intent"]].append(row)

    total = len(rows)
    sampled: list[dict[str, str]] = []

    # Sort for determinism
    intent_keys = sorted(by_intent.keys())
    remaining = n

    for i, intent in enumerate(intent_keys):
        intent_rows = sorted(by_intent[intent], key=lambda r: r["text"])
        # Proportional allocation, at least 1 per intent
        if i < len(intent_keys) - 1:
            count = max(1, round(len(intent_rows) / total * n))
            count = min(count, remaining - (len(intent_keys) - i - 1))
        else:
            count = remaining
        count = min(count, len(intent_rows))
        sampled.extend(rng.sample(intent_rows, count))
        remaining -= count

    return sampled


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Write a CSV file deterministically."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_datasets(source_path: Path, out_dir: Path) -> dict[str, int]:
    """Generate all evaluation datasets. Returns filename → row count."""
    rng = random.Random(42)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = load_source_dataset(source_path)
    counts: dict[str, int] = {}

    # 1. Separate by category
    metier_rows = [r for r in all_rows if r["intent"] in RETAINED_INTENTS]
    conseiller_rows = [r for r in all_rows if r["intent"] == CONSEILLER_INTENT]
    horsscope_rows = [r for r in all_rows
                      if r["intent"] not in RETAINED_INTENTS
                      and r["intent"] != CONSEILLER_INTENT]

    # 2. train.csv — all postulat examples (from e2e_intents.json config)
    # We use the verbatims from dataset.csv that match retained intents
    # but EXCLUDE heldout samples (will be separated below)
    # First, generate heldout sets, then train = metier - heldout

    # 3. heldout_metier.csv — 100 stratified from retained intents
    rng_metier = random.Random(42)
    heldout_metier = stratified_sample(metier_rows, 100, rng_metier)
    heldout_metier_texts = {r["text"] for r in heldout_metier}

    heldout_path = out_dir / "heldout_metier.csv"
    heldout_metier_sorted = sorted(heldout_metier, key=lambda r: (r["intent"], r["text"]))
    write_csv(heldout_path, heldout_metier_sorted, ["text", "intent"])
    counts["heldout_metier.csv"] = len(heldout_metier)

    # 4. train.csv — metier rows NOT in heldout
    train_rows = [r for r in metier_rows if r["text"] not in heldout_metier_texts]
    train_rows_sorted = sorted(train_rows, key=lambda r: (r["intent"], r["text"]))
    train_path = out_dir / "train.csv"
    write_csv(train_path, train_rows_sorted, ["text", "intent"])
    counts["train.csv"] = len(train_rows)

    # 5. heldout_conseiller.csv — all 126 parler_conseiller verbatims
    conseiller_sorted = sorted(conseiller_rows, key=lambda r: r["text"])
    conseiller_path = out_dir / "heldout_conseiller.csv"
    write_csv(conseiller_path, conseiller_sorted, ["text", "intent"])
    counts["heldout_conseiller.csv"] = len(conseiller_rows)

    # 6. heldout_horsscope.csv — 100 stratified from 32 non-selected intents
    rng_horsscope = random.Random(42)
    heldout_horsscope = stratified_sample(horsscope_rows, 100, rng_horsscope)
    heldout_horsscope_sorted = sorted(heldout_horsscope, key=lambda r: (r["intent"], r["text"]))
    horsscope_path = out_dir / "heldout_horsscope.csv"
    write_csv(horsscope_path, heldout_horsscope_sorted, ["text", "intent"])
    counts["heldout_horsscope.csv"] = len(heldout_horsscope)

    # 7. pieges.csv — 15 edge cases
    pieges_path = out_dir / "pieges.csv"
    write_csv(pieges_path, PIEGE_CASES, ["id", "text", "expected_behavior", "note"])
    counts["pieges.csv"] = len(PIEGE_CASES)

    # 8. HASHES.sha256
    hash_lines: list[str] = []
    for fname in sorted(counts.keys()):
        fpath = out_dir / fname
        sha = compute_sha256(fpath)
        hash_lines.append(f"{sha}  {fname}")

    hashes_path = out_dir / "HASHES.sha256"
    hashes_path.write_text("\n".join(hash_lines) + "\n", encoding="utf-8")

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frozen evaluation datasets (C1)")
    parser.add_argument("--source", required=True, help="Path to dataset.csv")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.is_file():
        print(f"Error: {source_path} not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    counts = generate_datasets(source_path, out_dir)

    print(f"Generated datasets in {out_dir}:")
    for fname, count in sorted(counts.items()):
        print(f"  {fname}: {count} rows")
    print(f"  HASHES.sha256: written")


if __name__ == "__main__":
    main()
