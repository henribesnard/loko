"""LOKO Bot — LLM streaming generation service.

Builds constrained prompts from retrieved chunks and streams
the response token-by-token.  Temperature is always 0.

The LLM provider is injected via protocol for testability.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from loko.bot.models import BotConfig, BotLLMConfig, Chunk, ToneProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM provider protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMProvider(Protocol):
    """Low-level LLM provider interface.

    Implementations wrap OpenAI, Anthropic, or any other LLM API.
    """

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens.

        Parameters
        ----------
        messages : list[dict]
            Chat messages with role/content.
        model : str
            Model identifier.
        temperature : float
            Always 0.0 for bot usage.
        max_tokens : int
            Maximum output tokens.
        timeout : int
            Request timeout in seconds.
        """
        ...


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_TONE_INSTRUCTIONS = {
    ToneProfile.FORMEL: (
        "Utilisez un ton professionnel et formel. "
        "Vouvoyez systématiquement l'utilisateur."
    ),
    ToneProfile.CHALEUREUX: (
        "Utilisez un ton chaleureux et empathique. "
        "Vouvoyez l'utilisateur mais restez accessible et bienveillant."
    ),
    ToneProfile.NEUTRE: (
        "Utilisez un ton neutre et factuel. "
        "Vouvoyez l'utilisateur et restez concis."
    ),
}

_TONE_INSTRUCTIONS_EN = {
    ToneProfile.FORMEL: (
        "Use a professional and formal tone. "
        "Address the user formally."
    ),
    ToneProfile.CHALEUREUX: (
        "Use a warm and empathetic tone. "
        "Be approachable and caring while remaining professional."
    ),
    ToneProfile.NEUTRE: (
        "Use a neutral, factual tone. "
        "Be concise and direct."
    ),
}


def build_system_prompt(config: BotConfig) -> str:
    """Build the system prompt for the LLM."""
    lang = config.language if config.language != "auto" else "fr"

    if lang == "fr":
        tone_instruction = _TONE_INSTRUCTIONS.get(
            config.tone_profile, _TONE_INSTRUCTIONS[ToneProfile.NEUTRE]
        )
        return (
            f"Vous êtes {config.name}, un assistant de service client.\n\n"
            "Règles strictes :\n"
            "1. Répondez UNIQUEMENT à partir des extraits de la base de connaissances "
            "fournis ci-dessous dans le contexte.\n"
            "2. Si le contexte ne contient pas d'information pertinente, "
            "dites clairement : \"Je n'ai pas d'information à ce sujet.\"\n"
            "3. Ne JAMAIS inventer d'information absente du contexte.\n"
            "4. Quand vous citez une source, incluez le lien : [Titre](URL)\n"
            "5. Répondez de manière concise et structurée.\n\n"
            f"Ton : {tone_instruction}\n"
            f"Langue de réponse : français"
        )
    else:
        tone_instruction = _TONE_INSTRUCTIONS_EN.get(
            config.tone_profile, _TONE_INSTRUCTIONS_EN[ToneProfile.NEUTRE]
        )
        return (
            f"You are {config.name}, a customer service assistant.\n\n"
            "Strict rules:\n"
            "1. Answer ONLY from the knowledge base excerpts provided "
            "below in the context.\n"
            "2. If the context does not contain relevant information, "
            "say clearly: \"I don't have information about this.\"\n"
            "3. NEVER make up information absent from the context.\n"
            "4. When citing a source, include the link: [Title](URL)\n"
            "5. Keep your response concise and structured.\n\n"
            f"Tone: {tone_instruction}\n"
            f"Response language: English"
        )


def build_user_prompt(
    query: str,
    chunks: list[Chunk],
    intent: str,
    sub_motif: str | None,
) -> str:
    """Build the user prompt with context chunks."""
    context_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source_ref = ""
        if chunk.source_url:
            title = chunk.source_title or "Source"
            source_ref = f" — [{title}]({chunk.source_url})"
        context_parts.append(f"[Extrait {i}{source_ref}]\n{chunk.text}")

    context_text = "\n\n".join(context_parts) if context_parts else "(Aucun extrait disponible)"

    sub_motif_line = f"\nSous-motif : {sub_motif}" if sub_motif else ""

    return (
        f"Contexte (base de connaissances) :\n{context_text}\n\n"
        f"---\n"
        f"Question utilisateur : {query}\n"
        f"Intention : {intent}{sub_motif_line}\n\n"
        f"Répondez en vous basant exclusivement sur le contexte ci-dessus."
    )


# ---------------------------------------------------------------------------
# Generator service
# ---------------------------------------------------------------------------

class BotGenerator:
    """LLM-based response generator with streaming."""

    def __init__(self, provider: LLMProvider, config: BotLLMConfig | None = None):
        self.provider = provider
        self.llm_config = config or BotLLMConfig()

    async def generate(
        self,
        query: str,
        chunks: list[Chunk],
        intent: str,
        sub_motif: str | None,
        config: BotConfig,
    ) -> AsyncIterator[str]:
        """Generate a response by streaming tokens.

        Parameters
        ----------
        query : str
            Original user query.
        chunks : list[Chunk]
            Retrieved and filtered chunks.
        intent : str
            Current intent id.
        sub_motif : str | None
            Current sub-motif id.
        config : BotConfig
            Bot configuration.

        Yields
        ------
        str
            One token at a time.
        """
        system_prompt = build_system_prompt(config)
        user_prompt = build_user_prompt(query, chunks, intent, sub_motif)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        llm = config.llm

        logger.info(
            "Starting generation: model=%s, chunks=%d, intent=%s",
            llm.model, len(chunks), intent,
        )

        async for token in self.provider.stream_chat(
            messages,
            model=llm.model,
            temperature=0.0,  # always frozen
            max_tokens=llm.max_tokens,
            timeout=llm.timeout,
        ):
            yield token

    def extract_sources(self, chunks: list[Chunk]) -> list[dict[str, str]]:
        """Extract unique source references from chunks."""
        seen: set[str] = set()
        sources: list[dict[str, str]] = []
        for chunk in chunks:
            if chunk.source_url and chunk.source_url not in seen:
                seen.add(chunk.source_url)
                sources.append({
                    "url": chunk.source_url,
                    "title": chunk.source_title or chunk.source_url,
                })
        return sources
