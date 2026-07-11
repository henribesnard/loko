"""LOKO Bot — Template engine and default library.

Templates are pure string interpolation (str.format_map).
No LLM involved — determinism by design.

Default texts are provided per tone profile (formel/chaleureux/neutre)
and per language (FR/EN).
"""

from __future__ import annotations

import re
from typing import Any

from loko.bot.models import (
    ALLOWED_TEMPLATE_VARIABLES,
    MessageTemplate,
    TemplateKey,
    ToneProfile,
)

# ---------------------------------------------------------------------------
# Safe renderer
# ---------------------------------------------------------------------------

_VAR_PATTERN = re.compile(r"\{(\w+)\}")


class TemplateRenderError(Exception):
    """Raised when a template variable is unknown or missing."""


def render(template_text: str, variables: dict[str, str]) -> str:
    """Render a template with safe variable interpolation.

    Raises TemplateRenderError if the template references a variable
    not in ALLOWED_TEMPLATE_VARIABLES.
    """
    used_vars = set(_VAR_PATTERN.findall(template_text))
    unknown = used_vars - ALLOWED_TEMPLATE_VARIABLES
    if unknown:
        raise TemplateRenderError(f"Unknown template variables: {unknown}")

    # Provide empty string for allowed but missing variables
    safe_vars = {k: variables.get(k, "") for k in ALLOWED_TEMPLATE_VARIABLES}
    safe_vars.update(variables)
    return template_text.format_map(safe_vars)


def render_template(
    template: MessageTemplate,
    language: str,
    variables: dict[str, str] | None = None,
) -> str:
    """Render a MessageTemplate for the given language."""
    text = template.text_fr if language == "fr" else template.text_en
    return render(text, variables or {})


# ---------------------------------------------------------------------------
# Default template library
# ---------------------------------------------------------------------------

_DEFAULTS: dict[ToneProfile, dict[TemplateKey, tuple[str, str, list[str]]]] = {
    # Each value: (text_fr, text_en, [variables_used])

    ToneProfile.NEUTRE: {
        TemplateKey.PRESENTATION: (
            "Bonjour, je suis {nom_bot}. Je peux vous aider sur les sujets suivants : {intentions_gerees}. Comment puis-je vous aider ?",
            "Hello, I am {nom_bot}. I can help you with the following topics: {intentions_gerees}. How can I help you?",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.CLARIFICATION_INTER: (
            "Votre demande concerne-t-elle l'un de ces sujets ?",
            "Does your request concern one of these topics?",
            [],
        ),
        TemplateKey.CLARIFICATION_INTRA: (
            "Pouvez-vous preciser votre demande ?",
            "Can you specify your request?",
            [],
        ),
        TemplateKey.HORS_PERIMETRE: (
            "Je ne suis pas en mesure de traiter cette demande. Pouvez-vous reformuler ou preciser votre question ?",
            "I am not able to handle this request. Could you rephrase or clarify your question?",
            [],
        ),
        TemplateKey.ENQUETE_SATISFACTION: (
            "Ai-je repondu a votre demande ?",
            "Did I answer your question?",
            [],
        ),
        TemplateKey.AUTRE_DEMANDE: (
            "Avez-vous une autre demande ?",
            "Do you have another question?",
            [],
        ),
        TemplateKey.FIN: (
            "Merci pour votre echange. Bonne journee.",
            "Thank you for the conversation. Have a good day.",
            [],
        ),
        TemplateKey.MISE_EN_RELATION: (
            "Je vous mets en relation avec un conseiller. Temps d'attente estime : {temps_attente} min.",
            "I am connecting you with an advisor. Estimated wait time: {temps_attente} min.",
            ["temps_attente"],
        ),
        TemplateKey.TIMEOUT: (
            "Votre session a expire par inactivite. N'hesitez pas a revenir si vous avez besoin d'aide.",
            "Your session has expired due to inactivity. Feel free to come back if you need help.",
            [],
        ),
        # ORC: graceful wind-down
        TemplateKey.AVANT_DERNIERE_DEMANDE: (
            "Je peux traiter encore une demande. Avez-vous une derniere question ?",
            "I can handle one more request. Do you have a last question?",
            ["nom_bot"],
        ),
        TemplateKey.CLOTURE_DOUCE: (
            "Nous avons traite ensemble : {resume_demandes}. Pour toute autre demande, un conseiller reste disponible : {lien_escalade}. Bonne journee !",
            "We have covered together: {resume_demandes}. For any other request, an advisor is available: {lien_escalade}. Have a good day!",
            ["nom_bot", "resume_demandes", "lien_escalade"],
        ),
        # GF: guardrail refusal and firm close
        TemplateKey.DEMANDE_INAPPROPRIEE: (
            "Je ne peux pas repondre a cette demande. Je peux vous aider sur : {intentions_gerees}.",
            "I cannot respond to this request. I can help you with: {intentions_gerees}.",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.FIN_FERME: (
            "Cette conversation ne peut pas se poursuivre. Pour toute demande concernant {intentions_gerees}, vous pouvez me recontacter.",
            "This conversation cannot continue. For any request regarding {intentions_gerees}, you can contact me again.",
            ["intentions_gerees"],
        ),
        # PRO: maintenance mode
        TemplateKey.MAINTENANCE: (
            "{nom_bot} est momentanement indisponible. Veuillez reessayer plus tard.",
            "{nom_bot} is temporarily unavailable. Please try again later.",
            ["nom_bot"],
        ),
    },

    ToneProfile.FORMEL: {
        TemplateKey.PRESENTATION: (
            "Bonjour. Je suis {nom_bot}, votre assistant. Je suis a votre disposition pour les sujets suivants : {intentions_gerees}. En quoi puis-je vous etre utile ?",
            "Good day. I am {nom_bot}, your assistant. I am at your disposal for the following topics: {intentions_gerees}. How may I assist you?",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.CLARIFICATION_INTER: (
            "Pourriez-vous preciser si votre demande concerne l'un des sujets suivants ?",
            "Could you clarify whether your request concerns one of the following topics?",
            [],
        ),
        TemplateKey.CLARIFICATION_INTRA: (
            "Afin de mieux vous orienter, pourriez-vous preciser la nature exacte de votre demande ?",
            "In order to better assist you, could you specify the exact nature of your request?",
            [],
        ),
        TemplateKey.HORS_PERIMETRE: (
            "Cette demande ne releve pas de mon perimetre de competence. Puis-je vous inviter a reformuler votre question ?",
            "This request falls outside my area of competence. May I invite you to rephrase your question?",
            [],
        ),
        TemplateKey.ENQUETE_SATISFACTION: (
            "Ma reponse a-t-elle satisfait votre demande ?",
            "Has my response satisfied your request?",
            [],
        ),
        TemplateKey.AUTRE_DEMANDE: (
            "Souhaitez-vous formuler une autre demande ?",
            "Would you like to submit another request?",
            [],
        ),
        TemplateKey.FIN: (
            "Je vous remercie pour cet echange. Je reste a votre disposition.",
            "Thank you for this exchange. I remain at your disposal.",
            [],
        ),
        TemplateKey.MISE_EN_RELATION: (
            "Je procede a votre mise en relation avec un conseiller. Le temps d'attente estime est de {temps_attente} minutes.",
            "I am proceeding to connect you with an advisor. The estimated wait time is {temps_attente} minutes.",
            ["temps_attente"],
        ),
        TemplateKey.TIMEOUT: (
            "Votre session a expire en raison d'une inactivite prolongee. N'hesitez pas a nous recontacter.",
            "Your session has expired due to prolonged inactivity. Please do not hesitate to contact us again.",
            [],
        ),
        TemplateKey.AVANT_DERNIERE_DEMANDE: (
            "Je suis en mesure de traiter une derniere demande. Souhaitez-vous poser une question supplementaire ?",
            "I am able to handle one last request. Would you like to ask an additional question?",
            ["nom_bot"],
        ),
        TemplateKey.CLOTURE_DOUCE: (
            "Nous avons aborde ensemble les sujets suivants : {resume_demandes}. Pour toute autre demande, un conseiller reste a votre disposition : {lien_escalade}. Bonne journee.",
            "We have covered the following topics together: {resume_demandes}. For any other request, an advisor remains at your disposal: {lien_escalade}. Good day.",
            ["nom_bot", "resume_demandes", "lien_escalade"],
        ),
        TemplateKey.DEMANDE_INAPPROPRIEE: (
            "Je ne suis pas en mesure de traiter cette demande. Mon perimetre de competence couvre : {intentions_gerees}.",
            "I am not able to process this request. My area of competence covers: {intentions_gerees}.",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.FIN_FERME: (
            "Cette conversation ne peut pas se poursuivre. Pour toute demande relevant de {intentions_gerees}, je vous invite a me recontacter.",
            "This conversation cannot continue. For any request regarding {intentions_gerees}, I invite you to contact me again.",
            ["intentions_gerees"],
        ),
        TemplateKey.MAINTENANCE: (
            "{nom_bot} est actuellement en maintenance. Nous vous prions de bien vouloir reessayer ulterieurement.",
            "{nom_bot} is currently under maintenance. We kindly ask you to try again later.",
            ["nom_bot"],
        ),
    },

    ToneProfile.CHALEUREUX: {
        TemplateKey.PRESENTATION: (
            "Bonjour ! Je suis {nom_bot}. Je suis la pour vous aider sur : {intentions_gerees}. Dites-moi comment je peux vous aider.",
            "Hi there! I'm {nom_bot}. I'm here to help you with: {intentions_gerees}. Tell me how I can help.",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.CLARIFICATION_INTER: (
            "J'aimerais bien vous aider. Votre question concerne-t-elle l'un de ces sujets ?",
            "I'd love to help. Does your question concern one of these topics?",
            [],
        ),
        TemplateKey.CLARIFICATION_INTRA: (
            "Pour mieux vous aider, pouvez-vous me preciser votre demande ?",
            "To help you better, can you clarify your request for me?",
            [],
        ),
        TemplateKey.HORS_PERIMETRE: (
            "Je ne suis malheureusement pas en mesure de vous aider sur ce sujet. Pouvez-vous essayer de reformuler ?",
            "Unfortunately, I'm not able to help with this topic. Could you try rephrasing?",
            [],
        ),
        TemplateKey.ENQUETE_SATISFACTION: (
            "Est-ce que ma reponse vous a aide ?",
            "Did my answer help you?",
            [],
        ),
        TemplateKey.AUTRE_DEMANDE: (
            "Avez-vous une autre question ? Je suis toujours la !",
            "Do you have another question? I'm still here!",
            [],
        ),
        TemplateKey.FIN: (
            "Merci et a bientot ! N'hesitez pas a revenir.",
            "Thanks and see you soon! Don't hesitate to come back.",
            [],
        ),
        TemplateKey.MISE_EN_RELATION: (
            "Je vous passe un conseiller, il sera la dans environ {temps_attente} minutes.",
            "I'm connecting you with an advisor, they'll be with you in about {temps_attente} minutes.",
            ["temps_attente"],
        ),
        TemplateKey.TIMEOUT: (
            "On dirait que vous etes parti. Revenez quand vous voulez, je serai la !",
            "Looks like you've left. Come back anytime, I'll be here!",
            [],
        ),
        TemplateKey.AVANT_DERNIERE_DEMANDE: (
            "Je peux encore vous aider sur une derniere question. Qu'est-ce que je peux faire pour vous ?",
            "I can still help you with one last question. What can I do for you?",
            ["nom_bot"],
        ),
        TemplateKey.CLOTURE_DOUCE: (
            "On a bien avance ensemble ! Voici ce qu'on a couvert : {resume_demandes}. Si vous avez besoin d'autre chose, un conseiller est disponible : {lien_escalade}. A bientot !",
            "We made good progress together! Here's what we covered: {resume_demandes}. If you need anything else, an advisor is available: {lien_escalade}. See you soon!",
            ["nom_bot", "resume_demandes", "lien_escalade"],
        ),
        TemplateKey.DEMANDE_INAPPROPRIEE: (
            "Je ne peux malheureusement pas vous aider la-dessus. En revanche, je suis la pour : {intentions_gerees}.",
            "Unfortunately I can't help with that. However, I'm here for: {intentions_gerees}.",
            ["nom_bot", "intentions_gerees"],
        ),
        TemplateKey.FIN_FERME: (
            "Je suis desole, mais cette conversation doit s'arreter ici. Pour vos questions sur {intentions_gerees}, n'hesitez pas a revenir !",
            "I'm sorry, but this conversation has to end here. For your questions about {intentions_gerees}, don't hesitate to come back!",
            ["intentions_gerees"],
        ),
        TemplateKey.MAINTENANCE: (
            "{nom_bot} fait une petite pause. Revenez vite, je serai de retour !",
            "{nom_bot} is taking a short break. Come back soon, I'll be back!",
            ["nom_bot"],
        ),
    },
}


def get_default_templates(
    tone: ToneProfile,
) -> dict[TemplateKey, MessageTemplate]:
    """Return the full set of default templates for a tone profile."""
    tone_defaults = _DEFAULTS.get(tone, _DEFAULTS[ToneProfile.NEUTRE])
    result: dict[TemplateKey, MessageTemplate] = {}
    for key, (text_fr, text_en, variables) in tone_defaults.items():
        result[key] = MessageTemplate(
            key=key,
            text_fr=text_fr,
            text_en=text_en,
            variables=variables,
        )
    return result


def resolve_template(
    config_templates: dict[TemplateKey, MessageTemplate],
    key: TemplateKey,
    tone: ToneProfile,
) -> MessageTemplate:
    """Get a template from config, falling back to defaults."""
    if key in config_templates:
        return config_templates[key]
    defaults = get_default_templates(tone)
    if key in defaults:
        return defaults[key]
    raise KeyError(f"No template found for key '{key.value}' (tone: {tone.value})")
