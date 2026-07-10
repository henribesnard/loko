"""C2 — Pure decision logic for evaluation.

R1: This module delegates to loko.bot.decision.decide_l1() — the single
source of truth for L1 routing decisions. The `decide()` wrapper is kept
for backward compatibility with existing eval code.
"""

from __future__ import annotations

from loko.bot.decision import Decision, DecisionType, decide_l1
from loko.bot.models import BotConfig

# Re-export for backward compatibility
__all__ = ["Decision", "DecisionType", "decide"]


def decide(
    l1_scores: list[tuple[str, float]],
    config: BotConfig,
    *,
    is_reformulation: bool = False,
) -> Decision:
    """Apply L1 routing logic — delegates to loko.bot.decision.decide_l1().

    Parameters
    ----------
    l1_scores : list[(intent_id, score)]
        Sorted by descending score (output of classifier.classify_l1).
    config : BotConfig
        Bot configuration with thresholds in config.journey.
    is_reformulation : bool
        If True, a previous attempt was already hors_perimetre.

    Returns
    -------
    Decision
    """
    return decide_l1(l1_scores, config.journey, is_reformulation=is_reformulation)
