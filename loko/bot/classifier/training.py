"""LOKO Bot — Training orchestration, evaluation, and actionable advice.

Provides cross-validation, confusion matrix, and human-readable advice
for improving intent classification quality.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from loko.bot.classifier.manifest import (
    LevelInfo,
    compute_dataset_hash,
    compute_file_hashes,
    measure_inference_latency,
    write_manifest,
)
from loko.bot.classifier.model_store import get_model_dir
from loko.bot.classifier.setfit_service import (
    DEFAULT_BASE_MODEL,
    SetFitClassifier,
    prepare_l1_training_data,
    prepare_l2_training_data,
    resolve_base_model,
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
    """Head-only k-fold cross-validation (K3 performance fix).

    Strategy: train the sentence-transformer body ONCE on all data,
    encode all texts into embeddings, then cross-validate ONLY the
    logistic head (fast — seconds, not minutes). This keeps the
    confusion matrix honest for its purpose (detecting confused pairs)
    while reducing cost from k×train_body to 1×train_body + k×fit_head.

    If there are too few examples per class for k folds, falls back
    to leave-one-out.
    """
    import numpy as np
    from setfit import SetFitModel, Trainer, TrainingArguments
    from sklearn.linear_model import LogisticRegression
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

    # --- Step 1: Train body once on all data (contrastive) ---
    numeric_labels_all = [label_to_idx[l] for l in labels]
    ds_all = Dataset.from_dict({"text": texts, "label": numeric_labels_all})

    resolved = resolve_base_model(base_model)
    model = SetFitModel.from_pretrained(resolved, labels=unique_labels)
    args = TrainingArguments(
        num_iterations=20,
        num_epochs=1,
        batch_size=16,
    )
    trainer = Trainer(model=model, args=args, train_dataset=ds_all)
    trainer.train()

    # --- Step 2: Encode all texts into embeddings ---
    embeddings = model.model_body.encode(texts, show_progress_bar=False)
    embeddings = np.array(embeddings)

    # --- Step 3: Stratified k-fold CV on the head only ---
    import random
    pairs_idx = list(range(len(texts)))
    rng = random.Random(42)
    rng.shuffle(pairs_idx)

    # Group by class for stratified folding
    class_buckets: dict[int, list[int]] = defaultdict(list)
    for i in pairs_idx:
        class_buckets[label_to_idx[labels[i]]].append(i)

    # Create stratified folds
    folds: list[list[int]] = [[] for _ in range(k)]
    for cls_indices in class_buckets.values():
        for i, idx in enumerate(cls_indices):
            folds[i % k].append(idx)

    all_true: list[int] = []
    all_pred: list[int] = []

    for fold_idx in range(k):
        val_indices = set(folds[fold_idx])
        train_idx = [i for i in range(len(texts)) if i not in val_indices]
        val_idx = list(val_indices)

        if not train_idx or not val_idx:
            continue

        X_train = embeddings[train_idx]
        y_train = [label_to_idx[labels[i]] for i in train_idx]
        X_val = embeddings[val_idx]
        y_val = [label_to_idx[labels[i]] for i in val_idx]

        # Fit logistic head only (very fast)
        head = LogisticRegression(max_iter=500, random_state=42)
        head.fit(X_train, y_train)
        preds = head.predict(X_val)

        all_true.extend(y_val)
        all_pred.extend(int(p) for p in preds)

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
    logger.info("Cross-validation completed in %.1fs (head-only CV on %d folds)", duration, k)

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

    # --- A4: Write manifest (atomic commit marker) ---
    _progress("writing_manifest")
    try:
        # Compute dataset hash
        dataset_hash = compute_dataset_hash(texts, labels)

        # Collect level info
        levels: dict[str, LevelInfo] = {}

        # L1
        l1_dir = get_model_dir(config.bot_id, "level1")
        levels["level1"] = LevelInfo(
            files=compute_file_hashes(l1_dir),
            labels=sorted(set(labels)),
            n_train_examples=len(texts),
        )

        # L2s
        for intent in config.intents:
            if intent.id in results.get("level2", {}) and "error" not in results["level2"].get(intent.id, {}):
                l2_dir = get_model_dir(config.bot_id, "level2", intent.id)
                l2_texts_i, l2_labels_i = prepare_l2_training_data(intent)
                levels[f"level2_{intent.id}"] = LevelInfo(
                    files=compute_file_hashes(l2_dir),
                    labels=sorted(set(l2_labels_i)),
                    n_train_examples=len(l2_texts_i),
                )

        # B3: Measure inference latency
        latency: dict[str, float] = {}
        try:
            latency = measure_inference_latency(config.bot_id)
            results["inference_latency_ms"] = latency
            logger.info(
                "Inference latency for bot %s: P50=%.1fms, P95=%.1fms",
                config.bot_id, latency.get("p50", 0), latency.get("p95", 0),
            )
        except Exception:
            logger.warning("Could not measure inference latency", exc_info=True)

        # Write manifest — LAST step
        write_manifest(
            bot_id=config.bot_id,
            levels=levels,
            dataset_hash=dataset_hash,
            train_metrics=results.get("evaluation"),
            inference_latency_ms=latency,
        )
        results["manifest"] = "written"
    except Exception:
        logger.exception("Failed to write manifest for bot %s", config.bot_id)
        results["manifest"] = "error"

    _progress("done", results)
    return results
