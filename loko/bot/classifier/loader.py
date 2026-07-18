"""Classifier and search backend loader (C8).

Extracted from loko/api/bot_public.py so that both the API server
and loko-eval can share the same loading logic without importing
FastAPI.
"""

from __future__ import annotations

import logging
from typing import Any

from loko.bot.errors import ComponentUnavailableError

logger = logging.getLogger(__name__)


def load_classifier(bot_id: str) -> Any:
    """Load the SetFit classifier for a bot (A3).

    Fail-closed: raises ComponentUnavailableError if the model is not
    trained or SetFit is not installed.  No mock fallback — tests must
    use register_orchestrator() to inject mocks.
    """
    try:
        from loko.bot.classifier.model_store import model_exists
        from loko.bot.classifier.setfit_service import SetFitClassifier
    except ImportError:
        raise ComponentUnavailableError(
            "classifier_l1",
            bot_id,
            "SetFit not installed (pip install loko[ml])",
        )

    if not model_exists(bot_id, "level1"):
        raise ComponentUnavailableError(
            "classifier_l1",
            bot_id,
            "Level 1 classifier not trained",
        )

    clf = SetFitClassifier(bot_id, "level1")
    if not clf.load():
        raise ComponentUnavailableError(
            "classifier_l1",
            bot_id,
            "Failed to load level 1 classifier from disk",
        )

    return SetFitClassifierAdapter(bot_id, clf)


def load_search_backend(bot_id: str) -> Any:
    """Load the search backend for a bot (R2-b, A3).

    Uses the persistent SQLite knowledge store.  Returns it even when
    empty (retrieval will fail and the bot will escalate).
    Tests should use register_orchestrator() instead (C7).
    """
    try:
        from loko.bot.knowledge_store import get_knowledge_store

        return get_knowledge_store(bot_id)
    except Exception:
        logger.warning("Could not load knowledge store for bot %s", bot_id)

    raise ComponentUnavailableError(
        "knowledge_store",
        bot_id,
        "Failed to initialize knowledge store",
    )


class SetFitClassifierAdapter:
    """Adapts SetFitClassifier to the ClassifierProtocol."""

    def __init__(self, bot_id: str, l1_classifier: Any, temperature: float = 1.0):
        self.bot_id = bot_id
        self._l1 = l1_classifier
        self._l2_cache: dict[str, Any] = {}
        self.temperature = temperature

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        scores = self._l1.classify(text)
        if self.temperature != 1.0:
            from loko.bot.classifier.calibration import apply_temperature_scaling

            scores = apply_temperature_scaling(scores, self.temperature)
        return scores

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        if intent_id not in self._l2_cache:
            try:
                from loko.bot.classifier.model_store import model_exists
                from loko.bot.classifier.setfit_service import SetFitClassifier

                if model_exists(self.bot_id, "level2", intent_id):
                    clf = SetFitClassifier(self.bot_id, "level2", intent_id)
                    clf.load()
                    self._l2_cache[intent_id] = clf
                else:
                    return []
            except ImportError:
                return []

        return self._l2_cache[intent_id].classify(text)
