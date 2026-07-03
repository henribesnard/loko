"""LOKO Bot — Training orchestration, evaluation, and actionable advice.

Provides cross-validation, confusion matrix, and human-readable advice
for improving intent classification quality.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from loko.bot.classifier.setfit_service import (
    DEFAULT_BASE_MODEL,
    SetFitClassifier,
    prepare_l1_training_data,
    prepare_l2_training_data,
)
from loko.bot.models import BotConfig, Intent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confusion matrix + advice
# ---------------------------------------------------------------------------

class EvaluationResult:
    """Holds cross-validation evaluation results."""

    def __init__(
        self,
        class_names: list[str],
        confusion_matrix: list[list[int]],
        accuracy: float,
        per_class_f1: dict[str, float],
        advice: list[str],
        duration_s: float,
    ):
        self.class_names = class_names
        self.confusion_matrix = confusion_matrix
        self.accuracy = accuracy
        self.per_class_f1 = per_class_f1
        self.advice = advice
        self.duration_s = duration_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_names": self.class_names,
            "confusion_matrix": self.confusion_matrix,
            "accuracy": round(self.accuracy, 4),
            "per_class_f1": {k: round(v, 4) for k, v in self.per_class_f1.items()},
            "advice": self.advice,
            "duration_s": round(self.duration_s, 2),
        }


def cross_validate(
    texts: list[str],
    labels: list[str],
    base_model: str = DEFAULT_BASE_MODEL,
    k: int = 5,
) -> EvaluationResult:
    """Run k-fold cross-validation and produce a confusion matrix + advice.

    If there are too few examples per class for k folds, falls back to
    leave-one-out.
    """
    from setfit import SetFitModel, Trainer, TrainingArguments
    from datasets import Dataset

    start = time.perf_counter()
    unique_labels = sorted(set(labels))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    n_classes = len(unique_labels)

    # Count per class
    class_counts: dict[str, int] = defaultdict(int)
    for l in labels:
        class_counts[l] += 1

    min_count = min(class_counts.values()) if class_counts else 0

    # Adjust k for leave-one-out if too few examples
    if min_count < k:
        k = max(2, min_count)

    # Build indexed pairs and shuffle deterministically
    import random
    pairs = list(zip(texts, labels))
    rng = random.Random(42)
    rng.shuffle(pairs)

    # Group by class for stratified folding
    class_buckets: dict[str, list[int]] = defaultdict(list)
    for i, (_, label) in enumerate(pairs):
        class_buckets[label].append(i)

    # Create stratified folds
    folds: list[list[int]] = [[] for _ in range(k)]
    for cls_indices in class_buckets.values():
        for i, idx in enumerate(cls_indices):
            folds[i % k].append(idx)

    # Cross-validate
    all_true: list[int] = []
    all_pred: list[int] = []

    for fold_idx in range(k):
        val_indices = set(folds[fold_idx])
        train_pairs = [(t, l) for i, (t, l) in enumerate(pairs) if i not in val_indices]
        val_pairs = [(t, l) for i, (t, l) in enumerate(pairs) if i in val_indices]

        if not train_pairs or not val_pairs:
            continue

        train_texts, train_labels = zip(*train_pairs)
        val_texts, val_labels = zip(*val_pairs)

        numeric_train = [label_to_idx[l] for l in train_labels]
        numeric_val = [label_to_idx[l] for l in val_labels]

        ds = Dataset.from_dict({"text": list(train_texts), "label": numeric_train})

        model = SetFitModel.from_pretrained(base_model, labels=unique_labels)
        args = TrainingArguments(
            num_iterations=10,  # faster for CV
            num_epochs=1,
            batch_size=16,
        )
        trainer = Trainer(model=model, args=args, train_dataset=ds)
        trainer.train()

        preds = model.predict(list(val_texts))
        pred_indices = [int(p) for p in preds]

        all_true.extend(numeric_val)
        all_pred.extend(pred_indices)

    # Build confusion matrix
    cm = [[0] * n_classes for _ in range(n_classes)]
    for true_idx, pred_idx in zip(all_true, all_pred):
        if 0 <= true_idx < n_classes and 0 <= pred_idx < n_classes:
            cm[true_idx][pred_idx] += 1

    # Compute accuracy
    correct = sum(cm[i][i] for i in range(n_classes))
    total = sum(sum(row) for row in cm)
    accuracy = correct / total if total > 0 else 0.0

    # Per-class F1
    per_class_f1: dict[str, float] = {}
    for i, cls_name in enumerate(unique_labels):
        tp = cm[i][i]
        fp = sum(cm[j][i] for j in range(n_classes)) - tp
        fn = sum(cm[i][j] for j in range(n_classes)) - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class_f1[cls_name] = f1

    # Generate advice
    advice = _generate_advice(unique_labels, cm, class_counts, per_class_f1)

    duration = time.perf_counter() - start

    return EvaluationResult(
        class_names=unique_labels,
        confusion_matrix=cm,
        accuracy=accuracy,
        per_class_f1=per_class_f1,
        advice=advice,
        duration_s=duration,
    )


def _generate_advice(
    class_names: list[str],
    cm: list[list[int]],
    class_counts: dict[str, int],
    per_class_f1: dict[str, float],
) -> list[str]:
    """Generate actionable advice from the confusion matrix."""
    advice: list[str] = []
    n = len(class_names)

    # 1. Find confused pairs
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            errors = cm[i][j]
            total_i = sum(cm[i])
            if total_i > 0 and errors / total_i > 0.2:
                advice.append(
                    f"'{class_names[i]}' et '{class_names[j]}' se confondent "
                    f"({errors}/{total_i} erreurs). "
                    f"Ajoutez des exemples discriminants entre ces deux intentions."
                )

    # 2. Under-represented classes
    for cls_name, count in class_counts.items():
        if count < 8:
            advice.append(
                f"'{cls_name}' n'a que {count} exemples. "
                f"Ajoutez-en pour atteindre au moins 15 (recommande)."
            )
        elif count < 15:
            advice.append(
                f"'{cls_name}' a {count} exemples. "
                f"15-20 exemples sont recommandes pour une classification fiable."
            )

    # 3. Low F1 classes
    for cls_name, f1 in per_class_f1.items():
        if f1 < 0.5:
            advice.append(
                f"'{cls_name}' a un F1 de {f1:.2f} (faible). "
                f"Verifiez la qualite et la distinctivite de ses exemples."
            )

    return advice


# ---------------------------------------------------------------------------
# Full training pipeline
# ---------------------------------------------------------------------------

def train_bot_classifiers(
    config: BotConfig,
    base_model: str = DEFAULT_BASE_MODEL,
    run_evaluation: bool = True,
    on_progress: Any = None,
) -> dict[str, Any]:
    """Train all classifiers for a bot (L1 + all L2s).

    Parameters
    ----------
    config : BotConfig
    base_model : str
    run_evaluation : bool
        If True, run cross-validation after training.
    on_progress : callable | None
        Optional callback(step: str, detail: dict) for progress reporting.

    Returns
    -------
    dict with training results and optional evaluation.
    """
    results: dict[str, Any] = {"level1": {}, "level2": {}, "evaluation": None}

    def _progress(step: str, detail: dict[str, Any] | None = None) -> None:
        if on_progress:
            on_progress(step, detail or {})

    # --- Level 1 ---
    _progress("l1_preparing")
    texts, labels = prepare_l1_training_data(config)

    if len(texts) == 0:
        results["level1"] = {"error": "No training data for L1"}
        return results

    _progress("l1_training", {"num_samples": len(texts), "num_classes": len(set(labels))})
    classifier = SetFitClassifier(config.bot_id, "level1")
    train_result = classifier.train(texts, labels, base_model=base_model)
    results["level1"] = train_result

    # --- Evaluation L1 ---
    if run_evaluation and len(texts) >= 4:
        _progress("l1_evaluating")
        eval_result = cross_validate(texts, labels, base_model=base_model)
        results["evaluation"] = eval_result.to_dict()

    # --- Level 2 (per intent with sub-motifs) ---
    for intent in config.intents:
        if not intent.sub_motifs:
            continue

        _progress("l2_preparing", {"intent": intent.id})
        l2_texts, l2_labels = prepare_l2_training_data(intent)

        if len(l2_texts) < 3:
            results["level2"][intent.id] = {"error": "Too few L2 examples"}
            continue

        _progress("l2_training", {"intent": intent.id, "num_samples": len(l2_texts)})
        l2_classifier = SetFitClassifier(config.bot_id, "level2", intent.id)
        l2_result = l2_classifier.train(l2_texts, l2_labels, base_model=base_model)
        results["level2"][intent.id] = l2_result

    _progress("done", results)
    return results
