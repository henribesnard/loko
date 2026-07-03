"""LOKO Bot — Built-in training examples for system intents.

The `demande_conseiller` intent is pre-trained with these examples,
merged automatically during training so the user doesn't have to
provide them.
"""

from __future__ import annotations

# FR + EN examples for the "demande_conseiller" system intent.
# These are merged with any user-provided examples at training time.
DEMANDE_CONSEILLER_EXAMPLES: list[str] = [
    # FR
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
    # EN
    "I want to speak with a human",
    "Transfer me to an agent please",
    "Can I talk to a real person",
    "I'd like to speak with a customer service representative",
    "Connect me with a human agent",
    "I want a real advisor not a bot",
    "Let me talk to someone",
    "Please transfer me to support",
    "I need to speak to a person",
    "Can you connect me with an operator",
]

# Minimal hors_perimetre fallback examples (user should add their own).
HORS_PERIMETRE_FALLBACK_EXAMPLES: list[str] = [
    # FR
    "Quel temps fait-il demain",
    "Raconte-moi une blague",
    "Quelle est la capitale de la France",
    "Combien font 2 plus 2",
    "Quel est le sens de la vie",
    "Parle-moi de politique",
    "Qui va gagner la coupe du monde",
    "Écris-moi un poème",
    # EN
    "What's the weather like tomorrow",
    "Tell me a joke",
    "What is the capital of France",
    "Write me a poem",
]
