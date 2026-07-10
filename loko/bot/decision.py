"""R1 — Shared L1 decision logic (single source of truth).

This module is the ONLY place where L1 routing decisions are made.
Both the runtime FSM (states.py) and the offline evaluation (eval/decision.py)
import and use `decide_l1()`.

No other module should implement score thresholding or routing logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from loko.bot.models import JourneyParams


DecisionType = Literal[
    "route",            # high-confidence -> direct routing
    "clarify_inter",    # medium-confidence -> propose 2 options
    "reject",           # hors_perimetre or below seuil_bas
    "escalate",         # demande_conseiller detected
]


@dataclass
class Decision:
    """Result of decide_l1()."""
    type: DecisionType
    intent: str | None = None
    score: float = 0.0
    candidates: list[tuple[str, float]] = field(default_factory=list)


def decide_l1(
    l1_scores: list[tuple[str, float]],
    journey: JourneyParams,
    *,
    is_reformulation: bool = False,
) -> Decision:
    """Apply L1 routing logic — pure function, no side effects.

    Parameters
    ----------
    l1_scores : list[(intent_id, score)]
        Sorted by descending score.
    journey : JourneyParams
        Thresholds (seuil_haut, seuil_bas, seuil_ecart_clarification, etc.).
    is_reformulation : bool
        If True, a previous attempt was already hors_perimetre (2nd chance
        used up) — escalate instead of reject.

    Returns
    -------
    Decision
        With type, intent, score, candidates.
    """
    if not l1_scores:
        return Decision(
            type="escalate" if is_reformulation else "reject",
            intent="hors_perimetre",
        )

    best_id, best_score = l1_scores[0]

    # Transverse: demande_conseiller -> escalate
    if best_id == "demande_conseiller":
        return Decision(type="escalate", intent="demande_conseiller", score=best_score)

    # hors_perimetre class -> reject (or escalate on 2nd attempt)
    if best_id == "hors_perimetre":
        if is_reformulation:
            return Decision(type="escalate", intent="hors_perimetre", score=best_score)
        return Decision(type="reject", intent="hors_perimetre", score=best_score)

    # Below seuil_bas -> reject
    if best_score < journey.seuil_bas:
        if is_reformulation:
            return Decision(type="escalate", intent=best_id, score=best_score)
        return Decision(type="reject", intent=best_id, score=best_score)

    # Above seuil_haut -> route directly (unless gap too small — M2)
    if best_score >= journey.seuil_haut:
        seuil_ecart = journey.seuil_ecart_clarification
        if seuil_ecart > 0 and len(l1_scores) >= 2:
            second_id, second_score = l1_scores[1]
            ecart = round(best_score - second_score, 9)
            if ecart < seuil_ecart:
                # Gap too small -> clarify instead of routing
                return Decision(
                    type="clarify_inter",
                    intent=best_id,
                    score=best_score,
                    candidates=[(best_id, best_score), (second_id, second_score)],
                )
        return Decision(type="route", intent=best_id, score=best_score)

    # Medium confidence -> clarification
    if len(l1_scores) >= 2:
        second_id, second_score = l1_scores[1]
        return Decision(
            type="clarify_inter",
            intent=best_id,
            score=best_score,
            candidates=[(best_id, best_score), (second_id, second_score)],
        )

    # Single score in medium range -> route
    return Decision(type="route", intent=best_id, score=best_score)
