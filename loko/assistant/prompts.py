"""LOKO Assistant — System prompts for A2 (training examples)."""

from __future__ import annotations


def build_a2_generate_prompt(
    label: str,
    definition: str,
    existing_examples: list[str],
    other_intents: list[dict[str, str]],
    count: int = 8,
) -> list[dict[str, str]]:
    """Build messages for generating new training examples."""
    others_desc = "\n".join(
        f"- {i['label']}: {i['definition']}" for i in other_intents
    )
    existing_str = "\n".join(f"- {e}" for e in existing_examples) if existing_examples else "(aucun)"

    system = (
        "Tu es un assistant spécialisé dans la conception de chatbots. "
        "Tu dois générer des exemples d'entraînement pour un classifieur d'intentions. "
        "Chaque exemple doit être une phrase courte et naturelle qu'un utilisateur réel "
        "pourrait écrire dans un chat. Varie le registre de langue, la formulation et "
        "la longueur. Évite les doublons sémantiques avec les exemples existants. "
        "Réponds UNIQUEMENT avec un tableau JSON, sans texte autour."
    )

    user = (
        f"Intention : \"{label}\"\n"
        f"Définition : \"{definition}\"\n\n"
        f"Exemples existants :\n{existing_str}\n\n"
        f"Autres intentions du bot (à ne PAS confondre) :\n{others_desc}\n\n"
        f"Génère {count} nouveaux exemples variés.\n"
        f"Format JSON attendu :\n"
        f'[{{"content": "phrase exemple", "rationale": "justification courte"}}]'
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_a2_discriminate_prompt(
    label: str,
    definition: str,
    candidates: list[str],
    other_intents: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build messages for evaluating candidate examples."""
    others_desc = "\n".join(
        f"- {i['label']}: {i['definition']}" for i in other_intents
    )
    candidates_str = "\n".join(f"- {c}" for c in candidates)

    system = (
        "Tu es un expert en NLU et classification d'intentions. "
        "Évalue chaque exemple candidat : est-il pertinent pour l'intention donnée ? "
        "Un bon exemple est sans ambiguïté, ne pourrait pas correspondre à une autre intention, "
        "et est formulé naturellement. "
        "Réponds UNIQUEMENT avec un tableau JSON, sans texte autour."
    )

    user = (
        f"Intention : \"{label}\"\n"
        f"Définition : \"{definition}\"\n\n"
        f"Autres intentions :\n{others_desc}\n\n"
        f"Exemples à évaluer :\n{candidates_str}\n\n"
        f"Pour chaque exemple, indique le verdict et une justification.\n"
        f"Format JSON attendu :\n"
        f'[{{"content": "phrase", "verdict": "keep" ou "drop", "rationale": "justification"}}]'
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_a2_review_prompt(
    label: str,
    definition: str,
    examples: list[str],
    other_intents: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build messages for reviewing existing examples quality."""
    others_desc = "\n".join(
        f"- {i['label']}: {i['definition']}" for i in other_intents
    )
    examples_str = "\n".join(f"- {e}" for e in examples)

    system = (
        "Tu es un expert en NLU et qualité des données d'entraînement. "
        "Analyse les exemples existants pour identifier : doublons sémantiques, "
        "exemples ambigus (qui pourraient correspondre à une autre intention), "
        "exemples hors périmètre, ou exemples mal formulés. "
        "Ne signale que les vrais problèmes. "
        "Réponds UNIQUEMENT avec un tableau JSON, sans texte autour."
    )

    user = (
        f"Intention : \"{label}\"\n"
        f"Définition : \"{definition}\"\n\n"
        f"Autres intentions :\n{others_desc}\n\n"
        f"Exemples à analyser :\n{examples_str}\n\n"
        f"Signale les problèmes trouvés.\n"
        f"Format JSON attendu :\n"
        f'[{{"content": "exemple problématique", "issue": "description du problème", '
        f'"suggestion": "correction suggérée ou \'supprimer\'"}}]\n'
        f"Si aucun problème, retourne un tableau vide []."
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
