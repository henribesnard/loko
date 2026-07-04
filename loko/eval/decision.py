"""C2 — Pure decision logic for evaluation, extracted from states.py.

This module replicates the same routing decisions as the FSM
(on_classification_l1_done) but in a stateless, testable function
suitable for offline evaluation.

The decide() function is the single entry point:
    decision = decide(l1_scores, config)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from loko.bot.models import BotConfig, JourneyParams


DecisionType = Literal[
    "route",            # high-confidence → direct routing
    "clarify_inter",    # medium-confidence → propose 2 options
    "reject",           # hors_perimetre or below seuil_bas
    "escalate",         # demande_conseiller detected
]


@dataclass
class Decision:
    """Result of the decide() function."""
    type: DecisionType
    intent: str | None = None
    score: float = 0.0
    candidates: list[tuple[str, float]] = field(default_factory=list)


def decide(
    l1_scores: list[tuple[str, float]],
    config: BotConfig,
    *,
    is_reformulation: bool = False,
) -> Decision:
    """Apply the same routing logic as on_classification_l1_done().

    This is a PURE function: no side effects, no session state.

    Parameters
    ----------
    l1_scores : list[(intent_id, score)]
        Sorted by descending score (output of classifier.classify_l1).
    config : BotConfig
        Bot configuration with thresholds in config.journey.
    is_reformulation : bool
        If True, a previous attempt was already hors_perimetre (2nd chance
        used up).

    Returns
    -------
    Decision
        With type, intent, score, candidates.
    """
    journey = config.journey

    if not l1_scores:
        return Decision(
            type="escalate" if is_reformulation else "reject",
            intent="hors_perimetre",
        )

    best_id, best_score = l1_scores[0]

    # Transverse: demande_conseiller → escalate
    if best_id == "demande_conseiller":
        return Decision(type="escalate", intent="demande_conseiller", score=best_score)

    # hors_perimetre class → reject
    if best_id == "hors_perimetre":
        if is_reformulation:
            return Decision(type="escalate", intent="hors_perimetre", score=best_score)
        return Decision(type="reject", intent="hors_perimetre", score=best_score)

    # Below seuil_bas → reject
    if best_score < journey.seuil_bas:
        if is_reformulation:
            return Decision(type="escalate", intent=best_id, score=best_score)
        return Decision(type="reject", intent=best_id, score=best_score)

    # Above seuil_haut → route directly
    if best_score >= journey.seuil_haut:
        return Decision(type="route", intent=best_id, score=best_score)

    # Medium confidence → clarification
    if len(l1_scores) >= 2:
        second_id, second_score = l1_scores[1]
        return Decision(
            type="clarify_inter",
            intent=best_id,
            score=best_score,
            candidates=[(best_id, best_score), (second_id, second_score)],
        )

    # Single score in medium range → route
    return Decision(type="route", intent=best_id, score=best_score)
