#!/usr/bin/env python3
"""E1 — Setup campaign bot for V2 training (protocol v2.2 compliant).

Reads train.csv and configures bot with ALL required intents:
  - 7 métier intents from train.csv
  - hors_perimetre (system) from train.csv
  - demande_conseiller (system, transverse) with built-in examples
  - L2 sub-motifs for help_account (5 labels)

This fixes the v0.3.7 config bug: bot had 8 intents instead of 9,
and no L2 sub-motifs, causing GNG-2 = 0% and L2 coverage failure.

Usage:
    python tools/setup_campaign_bot.py <bot_id> [--api-url URL] [--admin-token TOKEN]
    python tools/setup_campaign_bot.py <bot_id> --offline --bot-dir <path>

Exit code:
    0 — bot configured correctly (CE-9 conformity verified)
    1 — configuration error
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────────────────────────────────────
# L2 sub-motifs for help_account (5 labels, ≥ 3 examples each)
# Source: v0.3.6 campaign config (last valid campaign)
# ──────────────────────────────────────────────────────────────────────

HELP_ACCOUNT_SUB_MOTIFS = [
    {
        "id": "mot_de_passe_oublie",
        "label": "Mot de passe oublié",
        "definition": "Mot de passe perdu, oublié ou à renouveler",
        "examples": [
            "mot de passe perdu",
            "mot de passe oublié compte client",
            "récupération de mon mot de passe",
            "renouveler mon mot de passe",
            "je souhaite récupérer mon mot de passe pour accéder à mon compte Ameli",
        ],
    },
    {
        "id": "identifiants_perdus",
        "label": "Identifiants perdus",
        "definition": "Identifiant de connexion perdu ou inconnu",
        "examples": [
            "identifiant de connexion oublié",
            "je veux mes identifiants Ameli",
            "problème d'identifiant",
            "recevoir mes codes identifiant",
            "je voudrais un code d'accès au compte Ameli",
        ],
    },
    {
        "id": "compte_bloque",
        "label": "Compte bloqué",
        "definition": "Compte ou espace personnel bloqué/verrouillé",
        "examples": [
            "compte bloqué",
            "account locked",
            "débloquer mon compte personnel",
            "espace adhérent bloqué",
            "connexion espace personnel bloqué",
        ],
    },
    {
        "id": "premiere_connexion",
        "label": "Première connexion",
        "definition": "Création ou activation initiale du compte",
        "examples": [
            "activate my account",
            "création d'un compte en ligne",
            "comment créer un compte Ameli",
            "activation de mon espace client",
            "activation compte Santelis",
        ],
    },
    {
        "id": "probleme_technique",
        "label": "Problème technique",
        "definition": "Dysfonctionnement du site/appli",
        "examples": [
            "connexion impossible sur le site",
            "erreur de connexion",
            "espace personnel qui ne fonctionne pas",
            "dysfonctionnement de mon espace personnel en ligne",
            "impossible d'accéder à mon compte Ameli",
        ],
    },
]

# ──────────────────────────────────────────────────────────────────────
# Built-in demande_conseiller examples (mirrors builtin_examples.py)
# ──────────────────────────────────────────────────────────────────────

DEMANDE_CONSEILLER_EXAMPLES = [
    "Je veux parler à un conseiller",
    "Passez-moi un humain",
    "Je souhaite être mis en relation avec un agent",
    "Pouvez-vous me transférer à quelqu'un",
    "J'aimerais parler à une vraie personne",
    "Est-ce que je peux avoir un conseiller",
    "Mettez-moi en contact avec le service client",
    "Je préfère parler à un humain",
    "Transférez-moi à un agent s'il vous plaît",
    "Un conseiller humain s'il vous plaît",
    "Je ne veux pas parler à un robot",
    "Vous n'êtes qu'un bot, je veux un vrai conseiller",
    "Arrêtez avec vos réponses automatiques",
    "Donnez-moi un numéro de téléphone pour appeler",
    "Comment joindre un conseiller par téléphone",
]

# ──────────────────────────────────────────────────────────────────────
# Intent definitions (rich labels from v0.3.6 campaign)
# ──────────────────────────────────────────────────────────────────────

INTENT_DEFINITIONS = {
    "help_leave": "L'adhérent a une question liée à un arrêt de travail, maladie, indemnités journalières.",
    "help_contact": "L'adhérent veut modifier ses coordonnées (adresse, RIB, email).",
    "help_billing": "L'adhérent a une question sur ses cotisations (montant, calcul, paiement).",
    "hors_perimetre": "Demande hors du périmètre des intentions gérées par le bot.",
    "help_documents": "L'adhérent demande un document attestant de ses droits ou de sa couverture.",
    "help_cancellation": "L'adhérent veut résilier son contrat Santelis.",
    "help_account": "L'adhérent rencontre un besoin lié à son espace personnel en ligne ou à l'mobile app.",
    "help_transfer": "L'adhérent a une question sur la télétransmission Noemie entre Santelis et sécurité sociale.",
    "demande_conseiller": "L'adhérent demande explicitement à parler à un conseiller ou à un humain.",
}

SYSTEM_INTENTS = {"hors_perimetre", "demande_conseiller"}


def build_intents_from_train(train_csv: Path) -> list[dict]:
    """Build intent configs from train.csv + system intents + L2.

    Fixes the v0.3.7 bug:
    - Adds demande_conseiller as system intent with built-in examples
    - Marks hors_perimetre as system
    - Adds L2 sub-motifs to help_account
    """
    examples_by_intent: dict[str, list[str]] = defaultdict(list)

    with open(train_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            examples_by_intent[row["intent"]].append(row["text"])

    total_train = sum(len(ex) for ex in examples_by_intent.values())
    print(
        f"Loaded {total_train} examples across {len(examples_by_intent)} intents from train.csv"
    )

    intents = []

    # Add all intents from train.csv
    for intent_name in sorted(examples_by_intent.keys()):
        examples = examples_by_intent[intent_name]
        intent = {
            "id": intent_name,
            "label": intent_name.replace("_", " ").title(),
            "definition": INTENT_DEFINITIONS.get(intent_name, f"Intent {intent_name}"),
            "examples": examples,
            "sub_motifs": [],
            "is_system": intent_name in SYSTEM_INTENTS,
        }

        # Add L2 sub-motifs for help_account
        if intent_name == "help_account":
            intent["sub_motifs"] = HELP_ACCOUNT_SUB_MOTIFS
            print(
                f"  + help_account: {len(HELP_ACCOUNT_SUB_MOTIFS)} L2 sub-motifs added"
            )

        intents.append(intent)

    # Add demande_conseiller if not in train.csv (the v0.3.7 bug)
    if "demande_conseiller" not in examples_by_intent:
        print(
            "  + Adding missing system intent: demande_conseiller "
            f"({len(DEMANDE_CONSEILLER_EXAMPLES)} built-in examples)"
        )
        intents.append(
            {
                "id": "demande_conseiller",
                "label": "Demande conseiller",
                "definition": INTENT_DEFINITIONS["demande_conseiller"],
                "examples": DEMANDE_CONSEILLER_EXAMPLES,
                "sub_motifs": [],
                "is_system": True,
            }
        )

    return intents


def verify_conformity(intents: list[dict]) -> list[str]:
    """CE-9 conformity check (inline). Returns list of errors."""
    errors = []
    intent_ids = {i["id"] for i in intents}

    required = {
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
    missing = required - intent_ids
    if missing:
        errors.append(f"Missing intents: {sorted(missing)}")
    if len(intents) != 9:
        errors.append(f"Expected 9 intents, got {len(intents)}")

    for intent in intents:
        n_ex = len(intent.get("examples", []))
        if n_ex < 8:
            errors.append(f"Intent '{intent['id']}' has {n_ex} examples (min 8)")

    sel = next((i for i in intents if i["id"] == "help_account"), None)
    if sel:
        subs = sel.get("sub_motifs", [])
        if len(subs) < 5:
            errors.append(f"help_account L2 has {len(subs)} labels (need ≥ 5)")
    else:
        errors.append("help_account intent not found")

    # System flags
    for i in intents:
        if i["id"] in SYSTEM_INTENTS and not i.get("is_system"):
            errors.append(f"Intent '{i['id']}' should be marked is_system=true")

    return errors


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="E1 — Setup campaign bot (protocol v2.2 compliant)",
    )
    parser.add_argument("bot_id", help="Bot ID (UUID)")
    parser.add_argument(
        "--api-url", default="http://localhost:8001", help="LOKO API base URL"
    )
    parser.add_argument("--admin-token", default="test-token-v1", help="Admin token")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: write config.json directly instead of API",
    )
    parser.add_argument(
        "--bot-dir", default=None, help="Bot directory for offline mode"
    )
    parser.add_argument(
        "--train-csv",
        default=str(ROOT / "eval" / "datasets" / "train.csv"),
        help="Path to training CSV",
    )

    args = parser.parse_args()

    train_csv = Path(args.train_csv)
    if not train_csv.is_file():
        print(f"Error: {train_csv} not found", file=sys.stderr)
        sys.exit(1)

    # Build intents
    intents = build_intents_from_train(train_csv)

    # Verify conformity
    errors = verify_conformity(intents)
    if errors:
        print("\n[FAIL] CE-9 conformity check FAILED:")
        for err in errors:
            print(f"   - {err}")
        sys.exit(1)

    print(f"\n[OK] CE-9 conformity check succeeded: {len(intents)} intents, L2 OK")

    intent_summary = {i["id"]: len(i["examples"]) for i in intents}
    print(f"\nIntent summary: {json.dumps(intent_summary, indent=2)}")

    if args.offline:
        # Offline mode: write config.json directly
        bot_dir = (
            Path(args.bot_dir) if args.bot_dir else ROOT / "data" / "bots" / args.bot_id
        )
        config_path = bot_dir / "config.json"

        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            bot_dir.mkdir(parents=True, exist_ok=True)
            config = {
                "schema_version": 1,
                "bot_id": args.bot_id,
                "name": "Demo Campaign v2.2",
                "channel": "both",
                "language": "fr",
                "tone_profile": "neutre",
                "journey": {},
                "training": {},
                "templates": {},
                "knowledge_collection": "",
                "confidentiality_filter": ["public"],
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "api_key_set": False,
                    "max_tokens": 600,
                    "temperature": 0.0,
                    "timeout": 60,
                },
                "status": "draft",
            }

        config["intents"] = intents
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nConfig written to {config_path}")

    else:
        # API mode: update via HTTP
        import urllib.request

        url = f"{args.api_url}/api/bot/{args.bot_id}"
        req = urllib.request.Request(
            url,
            headers={"X-Admin-Token": args.admin_token},
        )

        with urllib.request.urlopen(req) as resp:
            config = json.loads(resp.read().decode("utf-8"))

        config["intents"] = intents

        data = json.dumps(config).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Admin-Token": args.admin_token,
            },
            method="PUT",
        )

        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(
                f"\nBot updated via API: {len(result.get('intents', []))} intents configured"
            )

    print(f"\nBot {args.bot_id} ready for training!")
    if not args.offline:
        print(
            f"Run: curl -X POST -H 'X-Admin-Token: {args.admin_token}' "
            f"{args.api_url}/api/bot/{args.bot_id}/train"
        )


if __name__ == "__main__":
    main()
