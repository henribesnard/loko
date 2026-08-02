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

    # A1: read calibration temperature from manifest
    temperature = 1.0
    ood_centroids = None
    ood_threshold = None
    try:
        from loko.bot.classifier.manifest import read_manifest

        manifest = read_manifest(bot_id)
        if manifest and "calibration" in manifest:
            temperature = float(manifest["calibration"].get("temperature", 1.0))
            logger.info(
                "Bot %s: using calibration temperature %.2f from manifest",
                bot_id,
                temperature,
            )
        else:
            logger.info(
                "Bot %s: manifest sans calibration — temperature neutre (1.0)",
                bot_id,
            )

        # E2: read OOD configuration from manifest
        if manifest and "ood" in manifest:
            ood_threshold = float(manifest["ood"].get("threshold", 0.5))
            logger.info(
                "Bot %s: OOD rejection enabled, threshold=%.4f",
                bot_id,
                ood_threshold,
            )

            # Load centroids from disk
            from loko.bot.classifier.model_store import get_model_dir
            from loko.bot.classifier.ood import load_centroids

            l1_dir = get_model_dir(bot_id, "level1")
            ood_centroids = load_centroids(l1_dir)
            if ood_centroids is None:
                logger.warning(
                    "Bot %s: OOD configured in manifest but centroids file missing",
                    bot_id,
                )
                ood_threshold = None
            else:
                logger.info(
                    "Bot %s: loaded %d OOD centroids",
                    bot_id,
                    len(ood_centroids),
                )
    except Exception:
        logger.warning(
            "Bot %s: could not read calibration from manifest — temperature neutre (1.0)",
            bot_id,
            exc_info=True,
        )

    return SetFitClassifierAdapter(
        bot_id,
        clf,
        temperature=temperature,
        ood_centroids=ood_centroids,
        ood_threshold=ood_threshold,
    )


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
    """Adapts SetFitClassifier to the ClassifierProtocol.

    E2: Now includes OOD rejection via centroid distance scoring.
    """

    def __init__(
        self,
        bot_id: str,
        l1_classifier: Any,
        temperature: float = 1.0,
        ood_centroids: dict[str, list[float]] | None = None,
        ood_threshold: float | None = None,
    ):
        self.bot_id = bot_id
        self._l1 = l1_classifier
        self._l2_cache: dict[str, Any] = {}
        self.temperature = temperature
        self._ood_centroids = ood_centroids
        self._ood_threshold = ood_threshold
        # E2: last computed OOD score (for tracing)
        self._last_ood_score: float | None = None

    @property
    def ood_enabled(self) -> bool:
        """Whether OOD rejection is active."""
        return self._ood_centroids is not None and self._ood_threshold is not None

    @property
    def last_ood_score(self) -> float | None:
        """The OOD score from the last classify_l1 call, or None."""
        return self._last_ood_score

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        """Classify text, with OOD pre-check if enabled.

        E2: If OOD is enabled and the text is out-of-distribution,
        returns [("hors_perimetre", ood_score)] to trigger rejection
        in decide_l1().
        """
        # E2: compute OOD score if centroids are available
        if self.ood_enabled:
            from loko.bot.classifier.ood import ood_score

            embedding = self._l1.encode([text])[0]
            self._last_ood_score = ood_score(embedding, self._ood_centroids)

            if self._last_ood_score >= self._ood_threshold:
                # OOD detected — return hors_perimetre without calling classifier
                return [("hors_perimetre", self._last_ood_score)]
        else:
            self._last_ood_score = None

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
