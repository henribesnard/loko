"""Tests for the LOKO assistant copilot module (L0 + L1/A2)."""

from __future__ import annotations

import json
import pytest

from loko.assistant.proposals import (
    AcceptItem,
    AcceptRequest,
    AssistantRequest,
    Proposal,
    SubMode,
    UseCase,
)
from loko.assistant.service import (
    _deduplicate,
    _normalize,
    _parse_json_array,
    handle_assistant_request,
)
from loko.bot.models import BotConfig, ExampleMeta, Intent, JourneyParams, ToneProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> BotConfig:
    return BotConfig(
        name="TestBot",
        intents=[
            Intent(
                id="livraison",
                label="Livraison",
                definition="Questions sur la livraison de colis",
                examples=[
                    "ou est mon colis",
                    "suivi livraison",
                    "quand vais-je recevoir ma commande",
                ],
            ),
            Intent(
                id="facturation",
                label="Facturation",
                definition="Questions sur les factures et paiements",
                examples=["je veux ma facture", "probleme de paiement"],
            ),
        ],
        journey=JourneyParams(),
        tone_profile=ToneProfile.NEUTRE,
    )


# ---------------------------------------------------------------------------
# Unit tests: JSON parsing
# ---------------------------------------------------------------------------


class TestParseJsonArray:
    def test_direct_array(self):
        text = '[{"content": "hello", "rationale": "test"}]'
        result = _parse_json_array(text)
        assert len(result) == 1
        assert result[0]["content"] == "hello"

    def test_markdown_fenced(self):
        text = """Here are the examples:
```json
[{"content": "bonjour", "rationale": "greeting"}]
```"""
        result = _parse_json_array(text)
        assert len(result) == 1
        assert result[0]["content"] == "bonjour"

    def test_with_preamble(self):
        text = """Sure! Here are some examples:
[{"content": "aide moi", "rationale": "help request"}]"""
        result = _parse_json_array(text)
        assert len(result) == 1
        assert result[0]["content"] == "aide moi"

    def test_empty_on_garbage(self):
        result = _parse_json_array("this is not json at all")
        assert result == []

    def test_empty_array(self):
        result = _parse_json_array("[]")
        assert result == []


# ---------------------------------------------------------------------------
# Unit tests: normalization and dedup
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercase_and_strip(self):
        assert _normalize("  Hello  World  ") == "hello world"

    def test_collapse_whitespace(self):
        assert _normalize("a   b\t c") == "a b c"


class TestDeduplicate:
    def test_removes_exact_duplicates(self):
        proposals = [
            {"content": "ou est mon colis"},
            {"content": "nouveau exemple"},
        ]
        existing = ["ou est mon colis"]
        result = _deduplicate(proposals, existing)
        assert len(result) == 1
        assert result[0]["content"] == "nouveau exemple"

    def test_removes_case_insensitive_duplicates(self):
        proposals = [{"content": "Ou Est Mon Colis"}]
        existing = ["ou est mon colis"]
        result = _deduplicate(proposals, existing)
        assert len(result) == 0

    def test_removes_intra_duplicates(self):
        proposals = [
            {"content": "example one"},
            {"content": "example one"},
        ]
        result = _deduplicate(proposals, [])
        assert len(result) == 1

    def test_keeps_unique(self):
        proposals = [
            {"content": "unique one"},
            {"content": "unique two"},
        ]
        result = _deduplicate(proposals, [])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Unit tests: ExampleMeta model
# ---------------------------------------------------------------------------


class TestExampleMeta:
    def test_defaults(self):
        meta = ExampleMeta(index=0)
        assert meta.origin == "user"

    def test_assistant_origin(self):
        meta = ExampleMeta(index=5, origin="assistant")
        assert meta.origin == "assistant"

    def test_intent_with_metadata(self):
        intent = Intent(
            id="test",
            label="Test",
            examples=["ex1", "ex2"],
            examples_metadata=[
                ExampleMeta(index=0, origin="user"),
                ExampleMeta(index=1, origin="assistant"),
            ],
        )
        assert len(intent.examples_metadata) == 2
        assert intent.examples_metadata[1].origin == "assistant"

    def test_intent_backward_compat(self):
        """Existing intents without metadata should work."""
        intent = Intent(id="test", label="Test", examples=["ex1"])
        assert intent.examples_metadata == []


# ---------------------------------------------------------------------------
# Unit tests: Proposal model
# ---------------------------------------------------------------------------


class TestProposalModel:
    def test_default_status_pending(self):
        p = Proposal(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="test",
            content="example text",
        )
        assert p.status == "pending"
        assert p.id  # auto-generated

    def test_serialization(self):
        p = Proposal(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="test",
            content="example text",
            rationale="good example",
        )
        data = p.model_dump(mode="json")
        assert data["content"] == "example text"
        assert data["use_case"] == "a2_examples"


# ---------------------------------------------------------------------------
# Integration: service.handle_assistant_request (mocked LLM)
# ---------------------------------------------------------------------------


class TestHandleAssistantRequest:
    @pytest.mark.asyncio
    async def test_generate_returns_proposals(self, sample_config, monkeypatch):
        """Generate sub-mode returns deduplicated proposals."""
        llm_response = json.dumps([
            {"content": "quand arrive mon colis", "rationale": "delivery timing"},
            {"content": "ou est mon colis", "rationale": "duplicate"},  # existing
            {"content": "je n'ai pas recu ma commande", "rationale": "missing order"},
        ])

        async def mock_llm(bot_id, config, messages, max_tokens=1200):
            return llm_response, {"prompt_tokens": 100, "completion_tokens": 50}

        monkeypatch.setattr(
            "loko.assistant.service.call_assistant_llm", mock_llm
        )

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="livraison",
        )
        result = await handle_assistant_request(
            "test-bot", sample_config, req
        )

        assert len(result.proposals) == 2  # "ou est mon colis" deduped
        contents = {p.content for p in result.proposals}
        assert "quand arrive mon colis" in contents
        assert "je n'ai pas recu ma commande" in contents
        assert "ou est mon colis" not in contents

    @pytest.mark.asyncio
    async def test_generate_with_markdown_fence(self, sample_config, monkeypatch):
        """LLM wrapping JSON in markdown fences should still work."""
        llm_response = """Here are some examples:
```json
[{"content": "mon colis est perdu", "rationale": "lost package"}]
```"""

        async def mock_llm(bot_id, config, messages, max_tokens=1200):
            return llm_response, {}

        monkeypatch.setattr(
            "loko.assistant.service.call_assistant_llm", mock_llm
        )

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="livraison",
        )
        result = await handle_assistant_request(
            "test-bot", sample_config, req
        )

        assert len(result.proposals) == 1
        assert result.proposals[0].content == "mon colis est perdu"

    @pytest.mark.asyncio
    async def test_review_returns_issues(self, sample_config, monkeypatch):
        """Review sub-mode returns quality issues."""
        llm_response = json.dumps([
            {
                "content": "suivi livraison",
                "issue": "trop court et vague",
                "suggestion": "reformuler en 'je voudrais suivre ma livraison'",
            }
        ])

        async def mock_llm(bot_id, config, messages, max_tokens=1200):
            return llm_response, {}

        monkeypatch.setattr(
            "loko.assistant.service.call_assistant_llm", mock_llm
        )

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.REVIEW,
            intent_id="livraison",
        )
        result = await handle_assistant_request(
            "test-bot", sample_config, req
        )

        assert len(result.proposals) == 1
        assert "trop court" in result.proposals[0].rationale

    @pytest.mark.asyncio
    async def test_discriminate_sets_rejected_status(
        self, sample_config, monkeypatch
    ):
        """Discriminate sub-mode sets status based on verdict."""
        llm_response = json.dumps([
            {"content": "good example", "verdict": "keep", "rationale": "clear"},
            {"content": "bad example", "verdict": "drop", "rationale": "ambiguous"},
        ])

        async def mock_llm(bot_id, config, messages, max_tokens=1200):
            return llm_response, {}

        monkeypatch.setattr(
            "loko.assistant.service.call_assistant_llm", mock_llm
        )

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.DISCRIMINATE,
            intent_id="livraison",
            context={"candidates": ["good example", "bad example"]},
        )
        result = await handle_assistant_request(
            "test-bot", sample_config, req
        )

        assert len(result.proposals) == 2
        kept = [p for p in result.proposals if p.status == "pending"]
        dropped = [p for p in result.proposals if p.status == "rejected"]
        assert len(kept) == 1
        assert len(dropped) == 1

    @pytest.mark.asyncio
    async def test_unknown_intent_404(self, sample_config, monkeypatch):
        """Request with unknown intent raises 404."""
        from fastapi import HTTPException

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="does_not_exist",
        )
        with pytest.raises(HTTPException) as exc_info:
            await handle_assistant_request("test-bot", sample_config, req)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_llm_response(self, sample_config, monkeypatch):
        """Empty LLM response returns empty proposals."""

        async def mock_llm(bot_id, config, messages, max_tokens=1200):
            return "I cannot generate examples.", {}

        monkeypatch.setattr(
            "loko.assistant.service.call_assistant_llm", mock_llm
        )

        req = AssistantRequest(
            use_case=UseCase.A2_EXAMPLES,
            sub_mode=SubMode.GENERATE,
            intent_id="livraison",
        )
        result = await handle_assistant_request(
            "test-bot", sample_config, req
        )

        assert len(result.proposals) == 0


# ---------------------------------------------------------------------------
# Unit tests: quota
# ---------------------------------------------------------------------------


class TestAssistantQuota:
    def test_increment_and_check(self, tmp_path, monkeypatch):
        """Quota increment and check work correctly."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

        from loko.assistant.quota import (
            get_assistant_usage,
            increment_assistant_usage,
        )

        assert get_assistant_usage("test-account") == 0
        increment_assistant_usage("test-account")
        assert get_assistant_usage("test-account") == 1
        increment_assistant_usage("test-account")
        assert get_assistant_usage("test-account") == 2

    def test_check_quota_raises_429(self, tmp_path, monkeypatch):
        """Exceeding quota raises 429."""
        from fastapi import HTTPException

        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("loko.assistant.quota.ASSISTANT_DEFAULT_QUOTA", 2)
        # Mock get_account to return trial plan
        monkeypatch.setattr(
            "loko.assistant.quota.get_account",
            lambda aid: {"plan": "trial"},
        )

        from loko.assistant.quota import (
            check_assistant_quota,
            increment_assistant_usage,
        )

        increment_assistant_usage("test-account")
        increment_assistant_usage("test-account")

        with pytest.raises(HTTPException) as exc_info:
            check_assistant_quota("test-account")
        assert exc_info.value.status_code == 429

    def test_ops_bypasses_quota(self, tmp_path, monkeypatch):
        """Ops accounts (empty account_id) bypass quota."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

        from loko.assistant.quota import check_assistant_quota

        # Should not raise
        check_assistant_quota("")


# ---------------------------------------------------------------------------
# Unit tests: prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_generate_prompt_structure(self):
        from loko.assistant.prompts import build_a2_generate_prompt

        messages = build_a2_generate_prompt(
            label="Livraison",
            definition="Questions sur la livraison",
            existing_examples=["ou est mon colis"],
            other_intents=[{"label": "Facturation", "definition": "Factures"}],
            count=5,
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Livraison" in messages[1]["content"]
        assert "ou est mon colis" in messages[1]["content"]
        assert "Facturation" in messages[1]["content"]
        assert "5" in messages[1]["content"]

    def test_review_prompt_structure(self):
        from loko.assistant.prompts import build_a2_review_prompt

        messages = build_a2_review_prompt(
            label="Livraison",
            definition="Questions sur la livraison",
            examples=["ex1", "ex2"],
            other_intents=[],
        )
        assert len(messages) == 2
        assert "ex1" in messages[1]["content"]

    def test_discriminate_prompt_structure(self):
        from loko.assistant.prompts import build_a2_discriminate_prompt

        messages = build_a2_discriminate_prompt(
            label="Livraison",
            definition="Questions sur la livraison",
            candidates=["candidate1"],
            other_intents=[],
        )
        assert len(messages) == 2
        assert "candidate1" in messages[1]["content"]
