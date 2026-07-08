#!/usr/bin/env python3
"""W4.2 — Generate enrichment training examples from W4.1 error patterns.

Produces realistic verbatims targeting the 4 error patterns identified:
  P1: Frontière services_en_ligne ↔ changement_coordonnees
  P2: demande_conseiller indirect (not explicit "parler à un conseiller")
  P3: Low-confidence clarification band (T04–T06 scores)
  P4: False rejects on realistic verbatims (typos, abbreviations, context)

Rules (from roadmap E2):
  - Verbatims are REALISTIC: oral turns, typos, contextual noise
  - Each example is tagged by target pattern
  - NEVER pulled from held-out datasets (interdit n°5)
  - Target: ~14->25-30 examples per class (~125->230-270 total)
  - Training budget: ≤ 300s (margin from 219s at 125 examples)

Usage:
    python tools/generate_enrichment_examples.py --output eval/datasets/enrichment_w42.csv
    python tools/generate_enrichment_examples.py --output eval/datasets/enrichment_w42.csv --verify

Exit code:
    0 — examples generated (and verified if --verify)
    1 — verification failed (intersection with held-out)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = ROOT / "eval" / "datasets"

# ──────────────────────────────────────────────────────────────────────
# Enrichment examples by intent, tagged by error pattern
#
# Pattern tags:
#   P1 = frontière services_en_ligne ↔ changement_coordonnees
#   P2 = demande_conseiller indirect
#   P3 = clarification band (formulations courtes, ambiguës)
#   P4 = faux rejets sur verbatims réalistes (abréviations, oral, fautes)
# ──────────────────────────────────────────────────────────────────────

ENRICHMENT_EXAMPLES: list[dict[str, str]] = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # arret_travail — 10 nouveaux exemples (P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "j'ai un souci avec mes AJ", "intent": "arret_travail", "pattern": "P4",
     "note": "abréviation AJ (allocations journalières)"},
    {"text": "formulaire 3116 à remplir pour la sécu", "intent": "arret_travail", "pattern": "P4",
     "note": "référence au formulaire cerfa 3116"},
    {"text": "prolongation de mon congé maladie", "intent": "arret_travail", "pattern": "P3",
     "note": "formulation directe sans mot-clé 'arrêt'"},
    {"text": "versement des indemnités en retard", "intent": "arret_travail", "pattern": "P3",
     "note": "focus sur le versement, pas l'arrêt"},
    {"text": "euh j'suis en maladie là et j'ai rien reçu", "intent": "arret_travail", "pattern": "P4",
     "note": "oral, hésitation, familier"},
    {"text": "demi traitement fonctionnaire maladie", "intent": "arret_travail", "pattern": "P4",
     "note": "spécifique fonction publique"},
    {"text": "mi-temps thérapeutique reprise", "intent": "arret_travail", "pattern": "P3",
     "note": "reprise après arrêt, contexte paramédical"},
    {"text": "CLM prolongé comment ça se passe", "intent": "arret_travail", "pattern": "P4",
     "note": "abréviation CLM (congé longue maladie)"},
    {"text": "maintien salaire pendant hospitalisation", "intent": "arret_travail", "pattern": "P3",
     "note": "variante sans mot 'arrêt'"},
    {"text": "subrogation employeur arret de travail", "intent": "arret_travail", "pattern": "P4",
     "note": "terme technique subrogation"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # justificatif_droits — 10 nouveaux exemples (P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "ma carte tiers payant", "intent": "justificatif_droits", "pattern": "P3",
     "note": "formulation courte, ambiguë"},
    {"text": "certificat d'adhésion à la mutuelle", "intent": "justificatif_droits", "pattern": "P3",
     "note": "variante 'adhésion' au lieu de 'affiliation'"},
    {"text": "j'ai perdu ma carte mutualiste", "intent": "justificatif_droits", "pattern": "P4",
     "note": "perte de document"},
    {"text": "attestation pour mon employeur", "intent": "justificatif_droits", "pattern": "P3",
     "note": "contexte employeur sans précision du type"},
    {"text": "besoin d'un justificatif de couverture en urgence", "intent": "justificatif_droits", "pattern": "P3",
     "note": "urgence + couverture"},
    {"text": "renouvellement de ma carte de mutuelle", "intent": "justificatif_droits", "pattern": "P4",
     "note": "confondu avec changement_coordonnees en v0.3.7"},
    {"text": "télécharger mon attestation sécu", "intent": "justificatif_droits", "pattern": "P3",
     "note": "action numérique + sécu"},
    {"text": "numéro de sécurité sociale sur la carte", "intent": "justificatif_droits", "pattern": "P4",
     "note": "question sur le contenu de la carte"},
    {"text": "document prouvant mes droits santé", "intent": "justificatif_droits", "pattern": "P3",
     "note": "formulation générique 'droits santé'"},
    {"text": "j'ai besoin d'une carte TP pour le médecin", "intent": "justificatif_droits", "pattern": "P4",
     "note": "abréviation TP (tiers payant)"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # services_en_ligne — 12 nouveaux exemples (P1, P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "problème connexion espace MGEN", "intent": "services_en_ligne", "pattern": "P4",
     "note": "mot-clé MGEN + connexion"},
    {"text": "l'appli MGEN marche plus", "intent": "services_en_ligne", "pattern": "P4",
     "note": "oral, 'marche plus' = dysfonctionnement"},
    {"text": "comment créer mon compte en ligne", "intent": "services_en_ligne", "pattern": "P1",
     "note": "frontière P1 — 'créer compte' = services, pas coordonnées"},
    {"text": "je veux accéder à mes remboursements en ligne", "intent": "services_en_ligne", "pattern": "P3",
     "note": "accès remboursements = espace client"},
    {"text": "mon espace adhérent ne s'ouvre pas", "intent": "services_en_ligne", "pattern": "P4",
     "note": "problème technique formulé familier"},
    {"text": "site internet MGEN en panne", "intent": "services_en_ligne", "pattern": "P4",
     "note": "diagnostic technique"},
    {"text": "j'arrive pas à me connecter sur Ameli", "intent": "services_en_ligne", "pattern": "P4",
     "note": "oral, forme négative familière"},
    {"text": "réinitialiser mes identifiants", "intent": "services_en_ligne", "pattern": "P3",
     "note": "action technique sans contexte"},
    {"text": "enregistrement compte personnel mutuelle", "intent": "services_en_ligne", "pattern": "P1",
     "note": "frontière P1 — 'enregistrement compte' = services"},
    {"text": "télécharger l'application MGEN", "intent": "services_en_ligne", "pattern": "P3",
     "note": "action mobile"},
    {"text": "activer mon espace en ligne MGEN", "intent": "services_en_ligne", "pattern": "P1",
     "note": "frontière P1 — activation = services"},
    {"text": "page blanche quand je me connecte", "intent": "services_en_ligne", "pattern": "P4",
     "note": "symptôme technique concret"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # changement_coordonnees — 8 nouveaux exemples (P1, P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "mettre à jour mon adresse suite à déménagement", "intent": "changement_coordonnees", "pattern": "P3",
     "note": "formulation contextuelle"},
    {"text": "nouvelle adresse mail à communiquer", "intent": "changement_coordonnees", "pattern": "P3",
     "note": "email sans mot 'changement'"},
    {"text": "modifier mon RIB de remboursement", "intent": "changement_coordonnees", "pattern": "P1",
     "note": "frontière P1 — RIB = coordonnées bancaires"},
    {"text": "j'ai déménagé faut mettre à jour", "intent": "changement_coordonnees", "pattern": "P4",
     "note": "oral, implicite"},
    {"text": "correction de mon numéro de téléphone", "intent": "changement_coordonnees", "pattern": "P3",
     "note": "téléphone = coordonnées"},
    {"text": "mon IBAN a changé", "intent": "changement_coordonnees", "pattern": "P4",
     "note": "IBAN au lieu de RIB"},
    {"text": "envoyer mes nouvelles coordonnées bancaires", "intent": "changement_coordonnees", "pattern": "P3",
     "note": "action + coordonnées bancaires"},
    {"text": "signaler un changement de domicile", "intent": "changement_coordonnees", "pattern": "P3",
     "note": "'signaler' = variante de 'déclarer'"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # cotisations — 6 nouveaux exemples (P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "montant mutuelle retraité", "intent": "cotisations", "pattern": "P4",
     "note": "cible l'erreur cotisation retraité -> arret_travail"},
    {"text": "combien je paye de mutuelle", "intent": "cotisations", "pattern": "P3",
     "note": "question directe sur le montant"},
    {"text": "ma cotisation a augmenté pourquoi", "intent": "cotisations", "pattern": "P3",
     "note": "contestation d'augmentation"},
    {"text": "prélèvement mutuelle sur ma retraite", "intent": "cotisations", "pattern": "P4",
     "note": "retraité + prélèvement, cible frontière avec arret_travail"},
    {"text": "échéancier des cotisations MGEN", "intent": "cotisations", "pattern": "P3",
     "note": "échéancier = planning de paiement"},
    {"text": "tarif de la mutuelle pour un couple", "intent": "cotisations", "pattern": "P3",
     "note": "variante 'tarif' au lieu de 'cotisation'"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # resiliation — 5 nouveaux exemples (P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "résilier la complémentaire de mon enfant", "intent": "resiliation", "pattern": "P4",
     "note": "cible l'erreur résilier complémentaire -> hors_perimetre"},
    {"text": "arrêter mon contrat mutuelle", "intent": "resiliation", "pattern": "P3",
     "note": "'arrêter' au lieu de 'résilier' (ambiguïté avec arret_travail)"},
    {"text": "quitter la MGEN", "intent": "resiliation", "pattern": "P3",
     "note": "formulation familière sans mot 'résiliation'"},
    {"text": "mettre fin à mon adhésion", "intent": "resiliation", "pattern": "P3",
     "note": "'mettre fin' = variante de résilier"},
    {"text": "résiliation prévoyance pour départ retraite", "intent": "resiliation", "pattern": "P4",
     "note": "cible l'erreur prévoyance actifs -> hors_perimetre"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # teletransmission_noemie — 5 nouveaux exemples (P3, P4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "liaison entre ma mutuelle et la sécu", "intent": "teletransmission_noemie", "pattern": "P3",
     "note": "formulation sans mot 'Noemie' ou 'télétransmission'"},
    {"text": "relier MGEN à mon compte Ameli", "intent": "teletransmission_noemie", "pattern": "P1",
     "note": "frontière avec services_en_ligne (compte Ameli)"},
    {"text": "pourquoi mes remboursements ne sont pas automatiques", "intent": "teletransmission_noemie", "pattern": "P3",
     "note": "symptôme de Noemie non activée"},
    {"text": "mise en place du tiers payant Noemie", "intent": "teletransmission_noemie", "pattern": "P4",
     "note": "tiers payant + Noemie = télétransmission"},
    {"text": "la mutuelle ne rembourse pas automatiquement", "intent": "teletransmission_noemie", "pattern": "P3",
     "note": "plainte implicite sur absence de Noemie"},

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # hors_perimetre — 8 nouveaux exemples (P3)
    # renforcer la frontière pour éviter les faux positifs
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {"text": "remboursement de mes lunettes", "intent": "hors_perimetre", "pattern": "P3",
     "note": "optique = hors périmètre bot"},
    {"text": "prise en charge d'une opération chirurgicale", "intent": "hors_perimetre", "pattern": "P3",
     "note": "hospitalisation = hors périmètre"},
    {"text": "remboursement dentaire prothèse", "intent": "hors_perimetre", "pattern": "P3",
     "note": "dentaire = hors périmètre"},
    {"text": "déclaration de grossesse", "intent": "hors_perimetre", "pattern": "P3",
     "note": "maternité = hors périmètre"},
    {"text": "comment me faire rembourser une consultation", "intent": "hors_perimetre", "pattern": "P3",
     "note": "remboursement soins = hors périmètre"},
    {"text": "devis pour un appareil auditif", "intent": "hors_perimetre", "pattern": "P3",
     "note": "appareillage = hors périmètre"},
    {"text": "garantie décès", "intent": "hors_perimetre", "pattern": "P3",
     "note": "prévoyance décès = hors périmètre"},
    {"text": "aide au logement étudiant", "intent": "hors_perimetre", "pattern": "P3",
     "note": "logement = hors périmètre"},
]


def verify_no_intersection(enrichment_texts: set[str]) -> list[str]:
    """Verify enrichment examples don't overlap with held-out datasets.

    Interdit n°5: never pull from held-out or train with held-out.
    """
    errors: list[str] = []

    held_out_files = [
        "heldout_metier.csv",
        "heldout_conseiller.csv",
        "heldout_horsscope.csv",
        "pieges.csv",
    ]

    for fname in held_out_files:
        fpath = DATASETS_DIR / fname
        if not fpath.exists():
            continue

        with open(fpath, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                text = row.get("text", "").strip().lower()
                if text in enrichment_texts:
                    errors.append(
                        f"INTERDIT n°5: '{text}' found in {fname} — "
                        f"REMOVE from enrichment"
                    )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="W4.2 — Generate enrichment training examples",
    )
    parser.add_argument("--output", "-o", required=True,
                        help="Output CSV path for enrichment examples")
    parser.add_argument("--verify", action="store_true",
                        help="Verify no intersection with held-out datasets")
    parser.add_argument("--merge-train", default=None,
                        help="Merge with existing train.csv and output combined")
    parser.add_argument("--stats", action="store_true",
                        help="Print statistics only, don't write file")

    args = parser.parse_args()

    # Statistics
    by_intent: dict[str, list[dict]] = {}
    by_pattern: dict[str, int] = {}

    for ex in ENRICHMENT_EXAMPLES:
        by_intent.setdefault(ex["intent"], []).append(ex)
        by_pattern[ex["pattern"]] = by_pattern.get(ex["pattern"], 0) + 1

    print(f"\nW4.2 Enrichment Examples Summary")
    print(f"{'='*50}")
    print(f"Total new examples: {len(ENRICHMENT_EXAMPLES)}")
    print(f"\nBy intent:")
    for intent in sorted(by_intent.keys()):
        examples = by_intent[intent]
        print(f"  {intent:30s} : {len(examples):2d} new examples")

    print(f"\nBy pattern:")
    for pattern, count in sorted(by_pattern.items()):
        labels = {"P1": "frontière inter-intent", "P2": "conseiller indirect",
                  "P3": "clarification band", "P4": "faux rejets réalistes"}
        print(f"  {pattern} ({labels.get(pattern, '?'):30s}) : {count:2d}")

    # Merge stats with existing train.csv
    train_path = DATASETS_DIR / "train.csv"
    if train_path.exists():
        existing: dict[str, int] = {}
        with open(train_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                intent = row["intent"]
                existing[intent] = existing.get(intent, 0) + 1

        print(f"\nProjected training set (train.csv + enrichment):")
        total_before = sum(existing.values())
        total_after = total_before + len(ENRICHMENT_EXAMPLES)
        for intent in sorted(set(list(existing.keys()) + list(by_intent.keys()))):
            before = existing.get(intent, 0)
            added = len(by_intent.get(intent, []))
            print(f"  {intent:30s} : {before:3d} -> {before + added:3d} (+{added})")
        print(f"  {'TOTAL':30s} : {total_before:3d} -> {total_after:3d} (+{len(ENRICHMENT_EXAMPLES)})")

    if args.stats:
        return

    # Verify no intersection with held-out
    enrichment_texts = {ex["text"].strip().lower() for ex in ENRICHMENT_EXAMPLES}
    intersection_errors = verify_no_intersection(enrichment_texts)

    if intersection_errors:
        print(f"\nFAIL: INTERDIT n°5 VIOLATION:")
        for err in intersection_errors:
            print(f"  {err}")
        sys.exit(1)

    print(f"\nOK: No intersection with held-out datasets (interdit n°5 OK)")

    # Write enrichment CSV
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "intent", "pattern", "note"])
        writer.writeheader()
        for ex in ENRICHMENT_EXAMPLES:
            writer.writerow(ex)

    print(f"\nEnrichment examples written to {out_path}")

    # Optionally merge with train.csv
    if args.merge_train:
        merge_path = Path(args.merge_train)
        all_rows: list[dict[str, str]] = []

        # Read existing train.csv
        if train_path.exists():
            with open(train_path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    all_rows.append({"text": row["text"], "intent": row["intent"]})

        # Add enrichment (train.csv only has text,intent columns)
        for ex in ENRICHMENT_EXAMPLES:
            all_rows.append({"text": ex["text"], "intent": ex["intent"]})

        # Check for duplicates
        seen = set()
        deduped = []
        for row in all_rows:
            key = row["text"].strip().lower()
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        with open(merge_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["text", "intent"])
            writer.writeheader()
            writer.writerows(deduped)

        print(f"Merged train written to {merge_path} ({len(deduped)} examples, {len(all_rows) - len(deduped)} duplicates removed)")

        # Compute hash for traceability
        sha256 = hashlib.sha256(merge_path.read_bytes()).hexdigest()
        print(f"SHA256: {sha256}")


if __name__ == "__main__":
    main()
