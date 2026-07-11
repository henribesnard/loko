"""R1 + R2 — Decision parity: runtime and eval use the same logic.

R1: decide_l1() is the single source of truth. Both states.py and
    eval/decision.py must produce identical decisions for the same inputs.
R2: Anti-regression guard — states.py must NOT contain inline threshold
    comparisons (seuil_haut, seuil_bas, seuil_ecart).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from loko.bot.decision import decide_l1
from loko.bot.models import BotConfig, JourneyParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_journey(**kwargs) -> JourneyParams:
    defaults = {"seuil_haut": 0.75, "seuil_bas": 0.45}
    defaults.update(kwargs)
    return JourneyParams(**defaults)


# ---------------------------------------------------------------------------
# R1: decide_l1 parity tests
# ---------------------------------------------------------------------------


class TestDecideL1:
    """Core decision logic tests — covers all branches."""

    def test_empty_scores_reject(self):
        j = _make_journey()
        d = decide_l1([], j)
        assert d.type == "reject"
        assert d.intent == "hors_perimetre"

    def test_empty_scores_reformulation_escalate(self):
        j = _make_journey()
        d = decide_l1([], j, is_reformulation=True)
        assert d.type == "escalate"

    def test_demande_conseiller_escalate(self):
        j = _make_journey()
        d = decide_l1([("demande_conseiller", 0.9)], j)
        assert d.type == "escalate"
        assert d.intent == "demande_conseiller"

    def test_hors_perimetre_reject(self):
        j = _make_journey()
        d = decide_l1([("hors_perimetre", 0.8)], j)
        assert d.type == "reject"
        assert d.intent == "hors_perimetre"

    def test_hors_perimetre_reformulation_escalate(self):
        j = _make_journey()
        d = decide_l1([("hors_perimetre", 0.8)], j, is_reformulation=True)
        assert d.type == "escalate"

    def test_low_confidence_reject(self):
        j = _make_journey(seuil_bas=0.45)
        d = decide_l1([("intent_a", 0.3)], j)
        assert d.type == "reject"

    def test_high_confidence_route(self):
        j = _make_journey(seuil_haut=0.75)
        d = decide_l1([("intent_a", 0.9)], j)
        assert d.type == "route"
        assert d.intent == "intent_a"

    def test_medium_confidence_clarify(self):
        j = _make_journey(seuil_haut=0.75, seuil_bas=0.45)
        d = decide_l1([("intent_a", 0.6), ("intent_b", 0.5)], j)
        assert d.type == "clarify_inter"
        assert len(d.candidates) == 2

    def test_medium_single_score_route(self):
        j = _make_journey(seuil_haut=0.75, seuil_bas=0.45)
        d = decide_l1([("intent_a", 0.6)], j)
        assert d.type == "route"

    # --- M2: seuil_ecart_clarification ---

    def test_ecart_zero_backward_compat(self):
        """Default ecart=0 -> no effect, routes normally."""
        j = _make_journey(seuil_haut=0.75, seuil_ecart_clarification=0.0)
        d = decide_l1([("a", 0.85), ("b", 0.84)], j)
        assert d.type == "route"

    def test_ecart_triggers_clarification(self):
        """Gap < seuil_ecart -> clarify instead of route."""
        j = _make_journey(seuil_haut=0.75, seuil_ecart_clarification=0.10)
        d = decide_l1([("a", 0.85), ("b", 0.80)], j)
        assert d.type == "clarify_inter"
        assert d.candidates[0][0] == "a"
        assert d.candidates[1][0] == "b"

    def test_ecart_allows_route_when_gap_large(self):
        """Gap >= seuil_ecart -> route."""
        j = _make_journey(seuil_haut=0.75, seuil_ecart_clarification=0.10)
        d = decide_l1([("a", 0.90), ("b", 0.70)], j)
        assert d.type == "route"

    def test_ecart_exact_threshold(self):
        """Gap == seuil_ecart -> route (not strict <)."""
        j = _make_journey(seuil_haut=0.75, seuil_ecart_clarification=0.10)
        d = decide_l1([("a", 0.85), ("b", 0.75)], j)
        assert d.type == "route"

    def test_ecart_single_score(self):
        """Only 1 score above seuil_haut -> route (ecart doesn't apply)."""
        j = _make_journey(seuil_haut=0.75, seuil_ecart_clarification=0.10)
        d = decide_l1([("a", 0.85)], j)
        assert d.type == "route"


# ---------------------------------------------------------------------------
# R1: eval/decision.decide() produces the same results as decide_l1()
# ---------------------------------------------------------------------------


class TestEvalDecisionParity:
    """Ensure eval/decision.decide() is just a thin wrapper around decide_l1()."""

    @pytest.mark.parametrize(
        "scores,ecart,expected_type",
        [
            ([("a", 0.9)], 0.0, "route"),
            ([("a", 0.85), ("b", 0.80)], 0.10, "clarify_inter"),
            ([("a", 0.85), ("b", 0.70)], 0.10, "route"),
            ([("hors_perimetre", 0.8)], 0.0, "reject"),
            ([("demande_conseiller", 0.5)], 0.0, "escalate"),
            ([], 0.0, "reject"),
            ([("a", 0.3)], 0.0, "reject"),
            ([("a", 0.6), ("b", 0.5)], 0.0, "clarify_inter"),
        ],
    )
    def test_eval_matches_decide_l1(self, scores, ecart, expected_type):
        from loko.eval.decision import decide

        journey = _make_journey(seuil_ecart_clarification=ecart)
        config = BotConfig(name="test", intents=[])

        # Override journey
        config = config.model_copy(update={"journey": journey})

        d_eval = decide(scores, config)
        d_shared = decide_l1(scores, journey)

        assert d_eval.type == d_shared.type == expected_type
        assert d_eval.intent == d_shared.intent
        assert d_eval.score == d_shared.score


# ---------------------------------------------------------------------------
# R2: Anti-regression guard — states.py must not inline threshold logic
# ---------------------------------------------------------------------------

_STATES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "loko" / "bot" / "states.py"
)

# Patterns that indicate inline threshold logic (should use decide_l1 instead)
_FORBIDDEN_PATTERNS = [
    re.compile(r"best_score\s*[<>]=?\s*journey\.seuil_haut"),
    re.compile(r"best_score\s*[<>]=?\s*journey\.seuil_bas"),
    re.compile(r"seuil_ecart"),
]


def test_states_no_inline_thresholds():
    """R2: states.py must not contain inline threshold comparisons.

    All L1 decision logic must be delegated to decide_l1().
    If this test fails, someone re-introduced threshold logic in states.py.
    """
    content = _STATES_PATH.read_text(encoding="utf-8")

    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.lstrip()
        if (
            stripped.startswith("#")
            or stripped.startswith("from ")
            or stripped.startswith("import ")
        ):
            continue
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append(f"  line {i}: {line.strip()}")

    assert not violations, (
        "states.py contains inline threshold logic that should be in decide_l1():\n"
        + "\n".join(violations)
    )


def test_states_imports_decide_l1():
    """R2: states.py must import decide_l1 from loko.bot.decision."""
    content = _STATES_PATH.read_text(encoding="utf-8")
    assert "from loko.bot.decision import decide_l1" in content, (
        "states.py must import decide_l1 from loko.bot.decision"
    )
