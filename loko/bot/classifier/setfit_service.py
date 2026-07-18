"""LOKO Bot — SetFit classification service.

Handles training and inference for both level 1 (intents) and
level 2 (sub-motifs) classifiers.

The service is designed to:
- Train on CPU in < 2 min for ~10 intents x 15 examples
- Infer in ~20-50 ms on CPU
- Be thread-safe for concurrent inference (read-only after load)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from loko.bot.classifier.builtin_examples import DEMANDE_CONSEILLER_EXAMPLES
from loko.bot.classifier.model_store import get_model_dir, model_exists
from loko.bot.models import BotConfig, Intent

logger = logging.getLogger(__name__)

DEFAULT_BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# A2: local path for the base model (set by Dockerfile or env)
_BASE_MODEL_PATH_ENV = "LOKO_BASE_MODEL_PATH"
_DEFAULT_BASE_MODEL_PATH = "/app/models/base/minilm"


def resolve_base_model(base_model: str = DEFAULT_BASE_MODEL) -> str:
    """Return a local path if the base model is cached on disk, else the hub ID.

    Checks LOKO_BASE_MODEL_PATH env var first, then the default
    container path.  If neither exists, returns the hub identifier
    (network access required).
    """
    env_path = os.environ.get(_BASE_MODEL_PATH_ENV, "")
    if env_path and Path(env_path).is_dir():
        logger.debug("Using local base model at %s", env_path)
        return env_path

    default = Path(_DEFAULT_BASE_MODEL_PATH)
    if default.is_dir():
        logger.debug("Using default local base model at %s", default)
        return str(default)

    # Fallback to hub ID — will need network access
    logger.debug("No local base model found, using hub ID: %s", base_model)
    return base_model


class SetFitClassifier:
    """Wraps a SetFit model for training and inference.

    One instance per classification level per bot.
    """

    def __init__(self, bot_id: str, level: str, intent_id: str | None = None):
        self.bot_id = bot_id
        self.level = level
        self.intent_id = intent_id
        self._model: Any = None  # SetFitModel once loaded
        self._label_map: dict[int, str] = {}  # numeric label -> class id
        self._id_map: dict[str, int] = {}  # class id -> numeric label

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        texts: list[str],
        labels: list[str],
        base_model: str = DEFAULT_BASE_MODEL,
        num_iterations: int = 20,
        num_epochs: int = 1,
        batch_size: int = 16,
    ) -> dict[str, Any]:
        """Train a SetFit model from scratch.

        Parameters
        ----------
        texts : list[str]
            Training sentences.
        labels : list[str]
            Corresponding class ids (same length as texts).
        base_model : str
            Sentence-transformer base model name.

        Returns
        -------
        dict with keys: num_classes, num_samples, duration_s
        """
        from setfit import SetFitModel, Trainer, TrainingArguments
        from datasets import Dataset

        start = time.perf_counter()

        # A2: resolve to local path if available
        resolved_model = resolve_base_model(base_model)

        # Build label mapping
        unique_labels = sorted(set(labels))
        self._id_map = {label: idx for idx, label in enumerate(unique_labels)}
        self._label_map = {idx: label for label, idx in self._id_map.items()}
        numeric_labels = [self._id_map[l] for l in labels]

        # Create dataset
        dataset = Dataset.from_dict({"text": texts, "label": numeric_labels})

        # Create model
        model = SetFitModel.from_pretrained(
            resolved_model,
            labels=unique_labels,
        )

        # Training arguments
        args = TrainingArguments(
            num_iterations=num_iterations,
            num_epochs=num_epochs,
            batch_size=batch_size,
            body_learning_rate=2e-5,
            head_learning_rate=1e-2,
        )

        # Train
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=dataset,
        )
        trainer.train()

        # Save
        model_dir = get_model_dir(self.bot_id, self.level, self.intent_id)
        model.save_pretrained(str(model_dir))
        self._save_label_map(model_dir)

        self._model = model
        duration = time.perf_counter() - start

        logger.info(
            "Trained %s classifier for bot %s: %d classes, %d samples in %.1fs",
            self.level,
            self.bot_id,
            len(unique_labels),
            len(texts),
            duration,
        )

        return {
            "num_classes": len(unique_labels),
            "num_samples": len(texts),
            "duration_s": round(duration, 2),
            "classes": unique_labels,
        }

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def classify(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Classify a text and return sorted (class_id, score) pairs.

        The model must be loaded (via load() or after train()).
        """
        if self._model is None:
            raise RuntimeError(
                f"Model not loaded for {self.level} "
                f"(bot_id={self.bot_id}, intent_id={self.intent_id})"
            )

        start = time.perf_counter()
        # M5: inference with torch.no_grad() for P95 latency optimization
        try:
            import torch

            with torch.no_grad():
                probs = self._model.predict_proba([text])[0]
        except ImportError:
            probs = self._model.predict_proba([text])[0]
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Build scored list
        scored: list[tuple[str, float]] = []
        for idx, prob in enumerate(probs):
            class_id = self._label_map.get(idx, str(idx))
            scored.append((class_id, float(prob)))

        scored.sort(key=lambda x: x[1], reverse=True)

        logger.debug(
            "Classification %s: top=%s score=%.3f latency=%.1fms",
            self.level,
            scored[0][0] if scored else "?",
            scored[0][1] if scored else 0,
            elapsed_ms,
        )

        return scored[:top_k]

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load a previously trained model from disk.  Returns True on success."""
        if not model_exists(self.bot_id, self.level, self.intent_id):
            return False

        from setfit import SetFitModel

        model_dir = get_model_dir(self.bot_id, self.level, self.intent_id)
        try:
            self._model = SetFitModel.from_pretrained(str(model_dir))
            # M5: set eval mode for faster inference (disables dropout, batch norm)
            try:
                self._model.model_body.eval()
            except Exception:
                pass
            self._load_label_map(model_dir)
            logger.info("Loaded %s model from %s", self.level, model_dir)
            return True
        except Exception:
            logger.exception("Failed to load model from %s", model_dir)
            return False

    def _save_label_map(self, model_dir: Any) -> None:
        """Save label mapping alongside the model."""
        import json
        from pathlib import Path

        label_path = Path(model_dir) / "label_map.json"
        # Convert int keys to str for JSON
        data = {str(k): v for k, v in self._label_map.items()}
        label_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load_label_map(self, model_dir: Any) -> None:
        """Load label mapping from disk."""
        import json
        from pathlib import Path

        label_path = Path(model_dir) / "label_map.json"
        if label_path.exists():
            data = json.loads(label_path.read_text(encoding="utf-8"))
            self._label_map = {int(k): v for k, v in data.items()}
            self._id_map = {v: int(k) for k, v in data.items()}


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def prepare_l1_training_data(config: BotConfig) -> tuple[list[str], list[str]]:
    """Build training texts and labels for L1 classification from a BotConfig.

    Automatically merges built-in demande_conseiller examples.
    """
    texts: list[str] = []
    labels: list[str] = []

    for intent in config.intents:
        examples = list(intent.examples)
        for sub_motif in intent.sub_motifs:
            examples.extend(sub_motif.examples)

        # Merge built-in examples for demande_conseiller
        if intent.id == "demande_conseiller":
            builtin = set(DEMANDE_CONSEILLER_EXAMPLES)
            existing = set(examples)
            for ex in builtin - existing:
                examples.append(ex)

        for ex in examples:
            texts.append(ex)
            labels.append(intent.id)

    return texts, labels


def prepare_l2_training_data(intent: Intent) -> tuple[list[str], list[str]]:
    """Build training texts and labels for L2 classification from an Intent."""
    texts: list[str] = []
    labels: list[str] = []

    for sm in intent.sub_motifs:
        for ex in sm.examples:
            texts.append(ex)
            labels.append(sm.id)

    return texts, labels
