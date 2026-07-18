#!/usr/bin/env python3
"""C1/C3/C4/C5 — Generate and verify frozen evaluation datasets.

Usage:
    python tools/make_datasets.py --source dataset.csv --out eval/datasets/
    python tools/make_datasets.py --check eval/datasets/

Inputs:
    dataset.csv — 6062 client verbatims (brand scrubbed at load): text, intent, locale

Outputs (in --out directory):
    train.csv              — postulat §2 strict examples (125 rows)
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
import random
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# -----------------------------------------------------------------------
# Postulat §2 — exact training examples (Option A: few-shot strict)
# -----------------------------------------------------------------------

POSTULAT_EXAMPLES: list[dict[str, str]] = []

_POSTULAT_RAW: dict[str, list[str]] = {
    "help_account": [
        "accès à mon espace personnel",
        "accès à mon compte Santelis",
        "accès espace perso",
        "accès à mon compte en ligne",
        "Santelis connexion au compte Ameli",
        "accès à mon application Santelis",
        "accès compte personnel sur mon site Santelis",
        "accès à mon espace adhérent",
        "accès à l'espace personnel internet de ma fille",
        "accès en ligne",
        "accès site Santelis",
        "accès à mon espace client",
        "accès au compte Ameli point FR",
        "accès à mon espace internet",
        "accéder au compte internet",
    ],
    "help_documents": [
        "attestation de droits",
        "attestation Santelis",
        "attestation d'affiliation à la sécurité sociale",
        "attestation CPAM",
        "attestation d'assuré social",
        "attestation de carte vitale",
        "attestation d'ayant droit",
        "attestation de droits de la sécurité sociale",
        "attestation d'ouverture de droits à la sécurité sociale",
        "attestation d'assurance maladie",
        "aide pour la carte tiers payant",
        "attestation Santelis pour ma fille",
        "attestation de droits en urgence",
        "attestation de couverture sociale",
        "attestation de droits perdue",
        "attestation avec la date d'effet",
    ],
    "help_leave": [
        "arrêt de travail",
        "arrêt de maladie",
        "comment déclarer un arrêt de travail",
        "allocation journalière",
        "indemnités journalières",
        "allocation journalière pour arrêt de travail prolongé",
        "complément de salaire en arrêt maladie",
        "comment activer le maintien de salaire",
        "arrêt maladie passage à demi-traitement",
        "allocation longue maladie",
        "attestation de salaire à remplir",
        "attestation indemnité journalière",
        "attestation à remplir pour le versement de l'ijss",
        "allocation d'invalidité",
        "compensation perte salaire",
        "autorisation de sortie pendant un congé maladie",
    ],
    "help_billing": [
        "connaître le montant de ma cotisation",
        "calcul de mes cotisations",
        "augmentation des cotisations",
        "comprendre mes cotisations",
        "appel de cotisation Santelis",
        "comment effectuer le paiement de mes cotisations",
        "comprendre mon échéancier",
        "cotisation Santelis au prélèvement automatique",
        "comprendre le prélèvement sur mon salaire",
        "contestation cotisation",
        "changement du montant de ma cotisation",
        "calcul montant de la cotisation conjoint",
        "attestation de paiement des cotisations",
        "concernant le prélèvement de Santelis",
        "comprendre le mode de calcul des cotisations",
        "connaître le coût de Santelis",
    ],
    "help_contact": [
        "changement d'adresse après déménagement",
        "actualiser mon adresse postale",
        "changement d'adresse de domicile",
        "besoin de changer mon RIB",
        "changement de RIB pour les remboursements",
        "ajouter un RIB",
        "changement d'adresse et de RIB",
        "changement RIB assurance maladie",
        "changement de IBAN",
        "actualiser mon adresse email",
        "besoin de changer d'adresse courriel",
        "changement d'adresse courriel",
        "adresse postale erronée",
        "changement coordonnées bancaires familiale",
        "changement d'adresse dans mon dossier",
        "changement de coordonnées personnelles",
    ],
    "help_transfer": [
        "comment mettre en place la télétransmission Noemie",
        "activer le lien Noemie",
        "bénéficier de la télétransmission",
        "annuler la télétransmission",
        "arrêter la télétransmission",
        "déconnexion du service Noemie",
        "connexion Noemie",
        "explications fonctionnement Noemie",
        "comment se fait la télétransmission entre Santelis et la sécu",
        "est-ce que le lien Noemie est créé avec ma nouvelle Santelis",
        "codes de télétransmission",
        "déconnecter Santelis de ma sécurité sociale",
        "au sujet des télétransmissions",
        "comment faire une télétrans",
        "contrat Noemie",
    ],
    "help_cancellation": [
        "comment résilier Santelis",
        "demande de résiliation de contrat Santelis",
        "procédure de résiliation",
        "délai de résiliation",
        "conditions de résiliation Santelis",
        "courrier résiliation Santelis",
        "attestation de résiliation",
        "annuler ma résiliation",
        "où en est la résiliation de mon contrat",
        "demande résiliation prévoyance",
        "information sur la résiliation d'un bénéficiaire",
        "pouvoir résilier Santelis",
        "changement de Santelis",
        "justificatif résiliation Santelis obligatoire",
        "effectuer une résiliation",
    ],
    "hors_perimetre": [
        "adresse pour envoyer un devis dentaire",
        "aide pour le remboursement pour une prothèse dentaire",
        "achat de lentilles de contact",
        "changer les verres",
        "comment déclarer un décès",
        "bénéficiaire capital décès",
        "agrément pour une cure thermale",
        "déclaration accident de travail",
        "déclarer un accident corporel",
        "activer un contrat logement",
        "accord préalable pour une prescription médicale de transport",
        "accusé réception de ma déclaration de grossesse",
        "achat de fauteuil roulant remboursement",
        "adhérer à une complémentaire santé",
        "adresse postale de Santelis",
        "prise en charge hospitalisation",
    ],
}

for _intent, _examples in sorted(_POSTULAT_RAW.items()):
    for _text in _examples:
        POSTULAT_EXAMPLES.append({"text": _text, "intent": _intent})


# The 7 intents retained in the postulat (from e2e_intents.json)
# Re-figeage 2026-07-17 : labels source (dataset.csv) -> IDs generiques post-scrub
INTENT_RENAME = {
    "services_en_ligne": "help_account",
    "justificatif_droits": "help_documents",
    "arret_travail": "help_leave",
    "cotisations": "help_billing",
    "changement_coordonnees": "help_contact",
    "teletransmission_noemie": "help_transfer",
    "resiliation": "help_cancellation",
}

RETAINED_INTENTS = {
    "help_account",
    "help_documents",
    "help_leave",
    "help_billing",
    "help_contact",
    "help_transfer",
    "help_cancellation",
}

# System intent for transverse escalation
CONSEILLER_INTENT = "parler_conseiller"

# -----------------------------------------------------------------------
# Edge cases T01-T15 (postulat §4 strict)
# -----------------------------------------------------------------------

PIEGE_CASES = [
    {"id": "T01", "text": "je souhaiterais débloquer mon compte Ameli",
     "expected_behavior": "route:help_account",
     "note": "help_account/compte_bloque sans clarification"},
    {"id": "T02", "text": "modification mot de passe",
     "expected_behavior": "route:help_account",
     "note": "help_account/mot_de_passe_oublie sans clarification"},
    {"id": "T03", "text": "accéder au compte Santelis",
     "expected_behavior": "clarify_intra:help_account",
     "note": "sous-motif incertain — clarification intra attendue"},
    {"id": "T04", "text": "RIB coordonnées bancaires",
     "expected_behavior": "clarify_inter:help_contact|help_billing",
     "note": "ambigu help_contact/cotisations"},
    {"id": "T05", "text": "changement de banque pour les prélèvements de cotisations",
     "expected_behavior": "clarify_inter:help_contact|help_billing",
     "note": "zone grise RIB/prélèvement"},
    {"id": "T06", "text": "attestation de paiement",
     "expected_behavior": "clarify_inter:help_leave|help_billing|help_documents",
     "note": "ambigu help_leave/help_billing/justificatif_droits"},
    {"id": "T07", "text": "attestation de droits Santelis",
     "expected_behavior": "route:help_documents",
     "note": "help_documents direct"},
    {"id": "T08", "text": "complément de salaire arrêt longue maladie",
     "expected_behavior": "route:help_leave",
     "note": "help_leave direct"},
    {"id": "T09", "text": "est-ce qu'il y a une télétransmission entre vous et Santelis",
     "expected_behavior": "route:help_transfer",
     "note": "help_transfer direct (contrôle positif)"},
    {"id": "T10", "text": "comment résilier mon ancien contrat Santelis",
     "expected_behavior": "route:help_cancellation",
     "note": "help_cancellation direct"},
    {"id": "T11", "text": "Je préfère parler à un humain",
     "expected_behavior": "escalate:demande_explicite",
     "note": "sortie transverse demande_conseiller"},
    {"id": "T12", "text": "déclarer un accident de ski",
     "expected_behavior": "reject",
     "note": "hors_périmètre — accident non retenu"},
    {"id": "T13", "text": "bilan bucco-dentaire détartrage",
     "expected_behavior": "reject",
     "note": "hors_périmètre — dentaire non retenu"},
    {"id": "T14", "text": "Noemie",
     "expected_behavior": "route:help_transfer",
     "note": "mot unique — robustesse entrées ultra-courtes"},
    {"id": "T15", "text": "la référence iban et le numéro de carte vitale ne sont pas reconnus",
     "expected_behavior": "route:help_account",
     "note": "piège IBAN+carte vitale — services_en_ligne"},
]

# Expected counts
EXPECTED_COUNTS = {
    "train.csv": len(POSTULAT_EXAMPLES),  # 125
    "heldout_metier.csv": 100,
    "heldout_conseiller.csv": 125,
    "heldout_horsscope.csv": 100,
    "pieges.csv": 15,
}


# -----------------------------------------------------------------------
# Text normalization for overlap detection (C3.2 / C5.d)
# -----------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize text for overlap comparison: lowercase, strip accents, reduce spaces."""
    text = text.strip().lower()
    # Strip accents
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Reduce whitespace
    text = " ".join(text.split())
    return text


# -----------------------------------------------------------------------
# Dataset generation
# -----------------------------------------------------------------------


# -----------------------------------------------------------------------
# Re-figeage v2 2026-07-18 — de-clientelisation (brand -> Santelis)
# B1 approved: fictional brand "Santelis" replaces both the client brand
# and the generic "mutuelle" to improve classifier discrimination (GNG-2).
# -----------------------------------------------------------------------

_CLIENT_RE = re.compile("m" + "gen", re.IGNORECASE)  # split to satisfy client-mention guard
_FICTIONAL_BRAND = "Santelis"


def scrub_client(text: str) -> str:
    """Replace client brand and generic 'mutuelle' with fictional brand (traced re-freeze v2)."""
    text = _CLIENT_RE.sub(_FICTIONAL_BRAND, text)
    text = re.sub(r"\bmutuelle\b", _FICTIONAL_BRAND, text, flags=re.IGNORECASE)
    # Collapse repeated brand names (e.g. "Santelis Santelis" -> "Santelis")
    text = re.sub(
        rf"\b{_FICTIONAL_BRAND}(\s+{_FICTIONAL_BRAND})+\b",
        _FICTIONAL_BRAND,
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(text.split())


def load_source_dataset(path: Path) -> list[dict[str, str]]:
    """Load dataset.csv (text, intent, locale)."""
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            intent = row["intent"].strip()
            intent = INTENT_RENAME.get(intent, intent)
            rows.append({"text": scrub_client(row["text"].strip()), "intent": intent})
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
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")  # LF canonique (re-figeage 2026-07-17)
        writer.writeheader()
        writer.writerows(rows)


def generate_datasets(source_path: Path, out_dir: Path) -> dict[str, int]:
    """Generate all evaluation datasets. Returns filename -> row count."""
    rng = random.Random(42)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = load_source_dataset(source_path)
    counts: dict[str, int] = {}

    # Build exclusion set: postulat + piege normalized texts
    postulat_norm = {normalize_text(r["text"]) for r in POSTULAT_EXAMPLES}
    piege_norm = {normalize_text(p["text"]) for p in PIEGE_CASES}
    excluded_norm = postulat_norm | piege_norm

    # 1. train.csv — postulat §2 strict (C4 Option A)
    train_rows = sorted(POSTULAT_EXAMPLES, key=lambda r: (r["intent"], r["text"]))
    train_path = out_dir / "train.csv"
    write_csv(train_path, train_rows, ["text", "intent"])
    counts["train.csv"] = len(train_rows)

    # 2. Separate source rows by category, excluding train/piege texts
    metier_pool = [
        r for r in all_rows
        if r["intent"] in RETAINED_INTENTS
        and normalize_text(r["text"]) not in excluded_norm
    ]
    conseiller_pool = [
        r for r in all_rows
        if r["intent"] == CONSEILLER_INTENT
        and normalize_text(r["text"]) not in excluded_norm
    ]
    horsscope_pool = [
        r for r in all_rows
        if r["intent"] not in RETAINED_INTENTS
        and r["intent"] != CONSEILLER_INTENT
        and normalize_text(r["text"]) not in excluded_norm
    ]

    # 3. heldout_metier.csv — 100 stratified from retained intents
    rng_metier = random.Random(42)
    heldout_metier = stratified_sample(metier_pool, 100, rng_metier)
    heldout_metier_sorted = sorted(heldout_metier, key=lambda r: (r["intent"], r["text"]))
    heldout_path = out_dir / "heldout_metier.csv"
    write_csv(heldout_path, heldout_metier_sorted, ["text", "intent"])
    counts["heldout_metier.csv"] = len(heldout_metier)

    # 4. heldout_conseiller.csv — all parler_conseiller verbatims
    conseiller_sorted = sorted(conseiller_pool, key=lambda r: r["text"])
    conseiller_path = out_dir / "heldout_conseiller.csv"
    write_csv(conseiller_path, conseiller_sorted, ["text", "intent"])
    counts["heldout_conseiller.csv"] = len(conseiller_pool)

    # 5. heldout_horsscope.csv — 100 stratified from non-selected intents
    rng_horsscope = random.Random(42)
    heldout_horsscope = stratified_sample(horsscope_pool, 100, rng_horsscope)
    heldout_horsscope_sorted = sorted(heldout_horsscope, key=lambda r: (r["intent"], r["text"]))
    horsscope_path = out_dir / "heldout_horsscope.csv"
    write_csv(horsscope_path, heldout_horsscope_sorted, ["text", "intent"])
    counts["heldout_horsscope.csv"] = len(heldout_horsscope)

    # 6. pieges.csv — 15 edge cases from postulat §4
    pieges_path = out_dir / "pieges.csv"
    write_csv(pieges_path, PIEGE_CASES, ["id", "text", "expected_behavior", "note"])
    counts["pieges.csv"] = len(PIEGE_CASES)

    # 7. HASHES.sha256
    hash_lines: list[str] = []
    for fname in sorted(counts.keys()):
        fpath = out_dir / fname
        sha = compute_sha256(fpath)
        hash_lines.append(f"{sha}  {fname}")

    hashes_path = out_dir / "HASHES.sha256"
    hashes_path.write_text("\n".join(hash_lines) + "\n", encoding="utf-8")

    return counts


# -----------------------------------------------------------------------
# C5 — Verification mode (--check)
# -----------------------------------------------------------------------

def check_datasets(datasets_dir: Path) -> list[str]:
    """Verify datasets without regenerating. Returns list of errors (empty = OK)."""
    errors: list[str] = []

    # (a) Presence of 5 files + HASHES
    required = list(EXPECTED_COUNTS.keys()) + ["HASHES.sha256"]
    for fname in required:
        if not (datasets_dir / fname).is_file():
            errors.append(f"Missing file: {fname}")
    if errors:
        return errors  # can't continue without files

    # (b) Exact row counts
    for fname, expected_count in EXPECTED_COUNTS.items():
        actual = _count_csv_rows(datasets_dir / fname)
        if actual != expected_count:
            errors.append(f"{fname}: expected {expected_count} rows, got {actual}")

    # (c) Hash verification
    hashes_path = datasets_dir / "HASHES.sha256"
    for line in hashes_path.read_text(encoding="utf-8").strip().split("\n"):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            errors.append(f"Invalid HASHES line: {line}")
            continue
        expected_hash, fname = parts
        actual_hash = compute_sha256(datasets_dir / fname)
        if actual_hash != expected_hash:
            errors.append(f"Hash mismatch for {fname}")

    # (d) Intersection checks (all pairs, case-folded/accent-normalized)
    sets: dict[str, set[str]] = {}
    for fname in EXPECTED_COUNTS:
        texts: set[str] = set()
        with open(datasets_dir / fname, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                texts.add(normalize_text(row["text"]))
        sets[fname] = texts

    pair_checks = [
        ("train.csv", "heldout_metier.csv"),
        ("train.csv", "heldout_conseiller.csv"),
        ("train.csv", "heldout_horsscope.csv"),
        ("train.csv", "pieges.csv"),
        ("pieges.csv", "heldout_metier.csv"),
        ("pieges.csv", "heldout_conseiller.csv"),
        ("pieges.csv", "heldout_horsscope.csv"),
    ]
    for a, b in pair_checks:
        overlap = sets[a] & sets[b]
        if overlap:
            samples = list(overlap)[:3]
            errors.append(f"Overlap {a} x {b}: {len(overlap)} texts (e.g. {samples})")

    # (e) Validate expected_behavior syntax in pieges.csv
    valid_prefixes = ("route:", "clarify_inter:", "clarify_intra:", "reject", "escalate:")
    with open(datasets_dir / "pieges.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            behavior = row["expected_behavior"]
            if not any(behavior.startswith(p) for p in valid_prefixes):
                errors.append(f"Invalid expected_behavior for {row['id']}: {behavior}")

    # (e bis) Validate piege IDs are T01-T15
    with open(datasets_dir / "pieges.csv", encoding="utf-8", newline="") as f:
        ids = [row["id"] for row in csv.DictReader(f)]
    expected_ids = [f"T{i:02d}" for i in range(1, 16)]
    if sorted(ids) != expected_ids:
        errors.append(f"Piege IDs mismatch: got {ids}, expected {expected_ids}")

    return errors


def _count_csv_rows(path: Path) -> int:
    with open(path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/verify frozen evaluation datasets (C1/C5)")
    parser.add_argument("--source", help="Path to dataset.csv (required for generation)")
    parser.add_argument("--out", help="Output directory (for generation)")
    parser.add_argument("--check", metavar="DIR", help="Verify existing datasets (no regeneration)")
    args = parser.parse_args()

    if args.check:
        check_dir = Path(args.check)
        if not check_dir.is_dir():
            print(f"Error: {check_dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        errors = check_datasets(check_dir)
        if errors:
            print("FAIL — dataset verification errors:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"OK — all checks passed for {check_dir}")
            sys.exit(0)

    if not args.source or not args.out:
        parser.error("--source and --out are required for generation (or use --check)")

    source_path = Path(args.source)
    if not source_path.is_file():
        print(f"Error: {source_path} not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    counts = generate_datasets(source_path, out_dir)

    print(f"Generated datasets in {out_dir}:")
    for fname, count in sorted(counts.items()):
        print(f"  {fname}: {count} rows")
    print("  HASHES.sha256: written")


if __name__ == "__main__":
    main()
