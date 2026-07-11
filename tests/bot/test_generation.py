"""Tests for the LLM generation service."""

from __future__ import annotations

import pytest

from loko.bot.generation import (
    BotGenerator,
    build_system_prompt,
    build_user_prompt,
)
from loko.testing.mocks import MockLLMProvider
from loko.bot.models import BotConfig, Chunk, ToneProfile


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_fr_prompt_contains_bot_name(self):
        config = BotConfig(name="MonBot", language="fr")
        prompt = build_system_prompt(config)
        assert "MonBot" in prompt
        assert "français" in prompt.lower()

    def test_en_prompt_contains_bot_name(self):
        config = BotConfig(name="MyBot", language="en")
        prompt = build_system_prompt(config)
        assert "MyBot" in prompt
        assert "English" in prompt

    def test_auto_language_defaults_to_fr(self):
        config = BotConfig(name="Bot", language="auto")
        prompt = build_system_prompt(config)
        assert "français" in prompt.lower()

    @pytest.mark.parametrize("tone", list(ToneProfile))
    def test_tone_instruction_included(self, tone):
        config = BotConfig(name="Bot", tone_profile=tone)
        prompt = build_system_prompt(config)
        # Each tone should produce a non-empty system prompt
        assert len(prompt) > 100

    def test_no_hallucination_instruction(self):
        config = BotConfig(name="Bot")
        prompt = build_system_prompt(config)
        assert "inventer" in prompt.lower() or "make up" in prompt.lower()


class TestBuildUserPrompt:
    def test_includes_chunks(self):
        chunks = [
            Chunk(
                text="Premier extrait", source_url="https://a.com", source_title="Doc A"
            ),
            Chunk(text="Deuxième extrait"),
        ]
        prompt = build_user_prompt("ma question", chunks, "livraison", None)
        assert "Premier extrait" in prompt
        assert "Deuxième extrait" in prompt
        assert "ma question" in prompt
        assert "livraison" in prompt

    def test_includes_source_urls(self):
        chunks = [
            Chunk(
                text="texte",
                source_url="https://example.com/article",
                source_title="Article",
            ),
        ]
        prompt = build_user_prompt("q", chunks, "intent", None)
        assert "https://example.com/article" in prompt
        assert "Article" in prompt

    def test_includes_sub_motif(self):
        prompt = build_user_prompt("q", [], "intent", "sous_motif")
        assert "sous_motif" in prompt

    def test_no_chunks_placeholder(self):
        prompt = build_user_prompt("q", [], "intent", None)
        assert "Aucun extrait" in prompt


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class TestBotGenerator:
    @pytest.mark.asyncio
    async def test_stream_tokens(self):
        provider = MockLLMProvider(response="Voici la réponse à votre question.")
        generator = BotGenerator(provider)
        config = BotConfig(name="TestBot")

        tokens = []
        async for token in generator.generate(
            query="test",
            chunks=[Chunk(text="contexte")],
            intent="livraison",
            sub_motif=None,
            config=config,
        ):
            tokens.append(token)

        full = "".join(tokens)
        assert "réponse" in full
        assert len(tokens) > 1  # should be multiple tokens

    @pytest.mark.asyncio
    async def test_provider_receives_messages(self):
        provider = MockLLMProvider(response="ok")
        generator = BotGenerator(provider)
        config = BotConfig(name="TestBot")

        async for _ in generator.generate(
            query="test",
            chunks=[],
            intent="livraison",
            sub_motif=None,
            config=config,
        ):
            pass

        assert len(provider.last_messages) == 2
        assert provider.last_messages[0]["role"] == "system"
        assert provider.last_messages[1]["role"] == "user"

    def test_extract_sources(self):
        generator = BotGenerator(MockLLMProvider())
        chunks = [
            Chunk(text="a", source_url="https://a.com", source_title="A"),
            Chunk(text="b", source_url="https://b.com", source_title="B"),
            Chunk(text="c", source_url="https://a.com"),  # duplicate
        ]
        sources = generator.extract_sources(chunks)
        assert len(sources) == 2
        assert sources[0]["url"] == "https://a.com"
        assert sources[1]["url"] == "https://b.com"

    def test_extract_sources_no_url(self):
        generator = BotGenerator(MockLLMProvider())
        chunks = [Chunk(text="no url")]
        sources = generator.extract_sources(chunks)
        assert len(sources) == 0
