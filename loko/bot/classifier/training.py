"""LOKO Bot — Training orchestration, evaluation, and actionable advice.

Provides cross-validation, confusion matrix, and human-readable advice
for improving intent classification quality.

L2: profiling per phase, configurable training budget, cached embeddings.
L3: CV on base model embeddings, margin-based advice.
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
from loko.bot.models import BotConfig

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
        advice: list[dict[str, Any]],
        duration_s: float,
    ):
        self.class_names = class_names
        self.confusion_matrix = confusion_matrix
        self.accuracy = accuracy
        self.per_class_f1 = per_class_f1
        self.advice = advice
        self.duration_s = duration_s
        self.extra_data: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        # W3.3: cv_method reflects multi-seed averaging if n_seeds > 1
        n_seeds = self.extra_data.get("n_seeds", 1)
        cv_method = (
            f"base_model_frozen_{n_seeds}seeds" if n_seeds > 1 else "base_model_frozen"
        )

        d: dict[str, Any] = {
            "class_names": self.class_names,
            "confusion_matrix": self.confusion_matrix,
            "accuracy": round(self.accuracy, 4),
            "per_class_f1": {k: round(v, 4) for k, v in self.per_class_f1.items()},
            "advice": self.advice,
            "cv_method": cv_method,
            "duration_s": round(self.duration_s, 2),
        }
        if self.extra_data:
            d.update(self.extra_data)
        return d


def cross_validate(
    texts: list[str],
    labels: list[str],
    base_model: str = DEFAULT_BASE_MODEL,
    k: int = 5,
    n_seeds: int = 3,
) -> EvaluationResult:
    """CV on base-model embeddings + margin analysis on final model (L3).

    Strategy (L3 revision — fixes K3.2 data leakage):
      1. Encode all texts with the FROZEN base model (pre-fine-tuning).
         These embeddings measure intrinsic separability, not post-training
         accuracy (which is inflated because the body saw all examples).
      2. Stratified k-fold CV of a logistic head on these base embeddings.
         The confusion matrix reveals genuinely confused pairs.
      3. Generate advice from both the confusion matrix and (later, when
         the trained model is available) margin analysis.

    W3.3 amendment (protocol v2.1):
      - Run CV with n_seeds different random partitions (default 3)
      - Average confusion matrices across seeds to reduce variance
      - This makes V2-5 signal measurement more robust on small datasets

    If there are too few examples per class for k folds, falls back
    to leave-one-out.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    start = time.perf_counter()
    unique_labels = sorted(set(labels))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    n_classes = len(unique_labels)

    class_counts: dict[str, int] = defaultdict(int)
    for l in labels:
        class_counts[l] += 1

    min_count = min(class_counts.values()) if class_counts else 0
    if min_count < k:
        k = max(2, min_count)

    # --- Step 1: Encode with FROZEN base model (no fine-tuning) ---
    from sentence_transformers import SentenceTransformer

    resolved = resolve_base_model(base_model)
    base_encoder = SentenceTransformer(resolved)
    embeddings = base_encoder.encode(texts, show_progress_bar=False)
    embeddings = np.array(embeddings)
    del base_encoder  # free memory

    encode_time = time.perf_counter() - start
    logger.info("Base-model encoding: %.1fs for %d texts", encode_time, len(texts))

    # --- Step 2: Multi-seed stratified k-fold CV (W3.3) ---
    import random

    # W3.3: Run CV with n_seeds different partitions, average confusion matrices
    cms_all_seeds: list[list[list[int]]] = []

    for seed_idx in range(n_seeds):
        seed = 42 + seed_idx  # Use 42, 43, 44 for n_seeds=3

        pairs_idx = list(range(len(texts)))
        rng = random.Random(seed)
        rng.shuffle(pairs_idx)

        class_buckets: dict[int, list[int]] = defaultdict(list)
        for i in pairs_idx:
            class_buckets[label_to_idx[labels[i]]].append(i)

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

            head = LogisticRegression(max_iter=500, random_state=seed)
            head.fit(X_train, y_train)
            preds = head.predict(X_val)

            all_true.extend(y_val)
            all_pred.extend(int(p) for p in preds)

        # Build confusion matrix for this seed
        cm_seed = [[0] * n_classes for _ in range(n_classes)]
        for true_idx, pred_idx in zip(all_true, all_pred):
            if 0 <= true_idx < n_classes and 0 <= pred_idx < n_classes:
                cm_seed[true_idx][pred_idx] += 1

        cms_all_seeds.append(cm_seed)

    # Average confusion matrices across seeds (W3.3)
    cm = [[0.0] * n_classes for _ in range(n_classes)]
    for i in range(n_classes):
        for j in range(n_classes):
            cm[i][j] = sum(cms[i][j] for cms in cms_all_seeds) / n_seeds

    # Round to integers for final confusion matrix
    cm = [[int(round(cm[i][j])) for j in range(n_classes)] for i in range(n_classes)]

    correct = sum(cm[i][i] for i in range(n_classes))
    total = sum(sum(row) for row in cm)
    accuracy = correct / total if total > 0 else 0.0

    per_class_f1: dict[str, float] = {}
    for i, cls_name in enumerate(unique_labels):
        tp = cm[i][i]
        fp = sum(cm[j][i] for j in range(n_classes)) - tp
        fn = sum(cm[i][j] for j in range(n_classes)) - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_class_f1[cls_name] = f1

    advice = _generate_advice(unique_labels, cm, class_counts, per_class_f1)

    duration = time.perf_counter() - start
    logger.info(
        "Cross-validation completed in %.1fs (base-model CV on %d folds × %d seeds, "
        "encode=%.1fs, cv=%.1fs)",
        duration,
        k,
        n_seeds,
        encode_time,
        duration - encode_time,
    )

    result = EvaluationResult(
        class_names=unique_labels,
        confusion_matrix=cm,
        accuracy=accuracy,
        per_class_f1=per_class_f1,
        advice=advice,
        duration_s=duration,
    )
    result.extra_data["n_seeds"] = n_seeds  # W3.3: track multi-seed averaging
    return result


def _generate_advice(
    class_names: list[str],
    cm: list[list[int]],
    class_counts: dict[str, int],
    per_class_f1: dict[str, float],
) -> list[dict[str, Any]]:
    """Generate structured advice from the confusion matrix (M1).

    Returns list of dicts, each with at least: type, suggestion.
    Pair entries also carry: pair, evidence, n_exemples_faibles.
    """
    advice: list[dict[str, Any]] = []
    n = len(class_names)

    # 1. Confused pairs from CV (off-diagonal >= 2)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            errors = cm[i][j]
            if errors >= 2:
                total_i = sum(cm[i])
                advice.append(
                    {
                        "type": "confused_pair",
                        "pair": sorted([class_names[i], class_names[j]]),
                        "evidence": "cv",
                        "n_exemples_faibles": errors,
                        "suggestion": (
                            f"'{class_names[i]}' et '{class_names[j]}' se confondent "
                            f"en CV base ({errors}/{total_i} erreurs). "
                            f"Ajoutez des exemples discriminants entre ces deux intentions."
                        ),
                    }
                )

    # 2. Under-represented classes
    for cls_name, count in sorted(class_counts.items()):
        if count < 8:
            advice.append(
                {
                    "type": "under_represented",
                    "intent": cls_name,
                    "n_exemples_faibles": count,
                    "suggestion": (
                        f"'{cls_name}' n'a que {count} exemples. "
                        f"Ajoutez-en pour atteindre au moins 15 (recommande)."
                    ),
                }
            )
        elif count < 15:
            advice.append(
                {
                    "type": "under_represented",
                    "intent": cls_name,
                    "n_exemples_faibles": count,
                    "suggestion": (
                        f"'{cls_name}' a {count} exemples. "
                        f"15-20 exemples sont recommandes pour une classification fiable."
                    ),
                }
            )

    # 3. Low F1 classes
    for cls_name, f1 in sorted(per_class_f1.items()):
        if f1 < 0.5:
            advice.append(
                {
                    "type": "low_f1",
                    "intent": cls_name,
                    "n_exemples_faibles": 0,
                    "suggestion": (
                        f"'{cls_name}' a un F1 de {f1:.2f} (faible). "
                        f"Verifiez la qualite et la distinctivite de ses exemples."
                    ),
                }
            )

    return advice


def _merge_and_sort_advice(
    cv_advice: list[dict[str, Any]],
    margin_advice: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """M1: merge CV and margin advice, deduplicate pairs, sort by severity.

    For pair advice: if the same pair appears in both CV and margin evidence,
    merge into a single entry with evidence="both".
    Sort: confused_pairs first (by n_exemples_faibles desc), then other types.
    """
    # Index margin advice by pair for merging
    margin_by_pair: dict[tuple[str, ...], dict[str, Any]] = {}
    for entry in margin_advice:
        if entry.get("type") == "confused_pair":
            key = tuple(sorted(entry.get("pair", [])))
            margin_by_pair[key] = entry

    merged: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, ...]] = set()

    # Process CV advice — merge with margin if same pair
    for entry in cv_advice:
        if entry.get("type") == "confused_pair":
            key = tuple(sorted(entry.get("pair", [])))
            if key in margin_by_pair:
                # Merge: use margin data (has verbatims) + note CV evidence
                m = margin_by_pair[key].copy()
                m["evidence"] = "both"
                m["n_exemples_faibles"] = max(
                    entry.get("n_exemples_faibles", 0),
                    m.get("n_exemples_faibles", 0),
                )
                merged.append(m)
                seen_pairs.add(key)
            else:
                merged.append(entry)
                seen_pairs.add(key)
        else:
            merged.append(entry)

    # Add margin-only pairs not yet seen
    for entry in margin_advice:
        if entry.get("type") == "confused_pair":
            key = tuple(sorted(entry.get("pair", [])))
            if key not in seen_pairs:
                merged.append(entry)
                seen_pairs.add(key)

    # Sort: confused_pairs first (by n_exemples_faibles desc), then others
    def _sort_key(entry: dict[str, Any]) -> tuple[int, int]:
        if entry.get("type") == "confused_pair":
            return (0, -entry.get("n_exemples_faibles", 0))
        return (1, 0)

    merged.sort(key=_sort_key)
    return merged


# ---------------------------------------------------------------------------
# Full training pipeline
# ---------------------------------------------------------------------------


def compute_margin_analysis(
    classifier: SetFitClassifier,
    texts: list[str],
    labels: list[str],
    *,
    margin_threshold: float = 0.15,
    max_verbatims: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """M1: compute top1-top2 margin for each example on the trained model.

    Returns
    -------
    weak_pairs : list[dict]
        Each dict: {pair, count, avg_margin, verbatims}.
        ALL pairs with at least 1 weak example, sorted by count desc.
    advice : list[dict]
        Structured advice entries for each weak pair.
    """
    from collections import Counter, defaultdict as ddict

    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_margins: ddict[tuple[str, str], list[float]] = ddict(list)
    pair_verbatims: ddict[tuple[str, str], list[str]] = ddict(list)

    for text, expected in zip(texts, labels):
        scores = classifier.classify(text, top_k=2)
        if len(scores) < 2:
            continue
        top1_id, top1_score = scores[0]
        top2_id, top2_score = scores[1]
        margin = top1_score - top2_score
        if margin < margin_threshold:
            pair = tuple(sorted([top1_id, top2_id]))
            pair_counts[pair] += 1
            pair_margins[pair].append(margin)
            pair_verbatims[pair].append(text)

    # Build structured weak_pairs sorted by count desc, then avg margin asc
    weak_pairs: list[dict[str, Any]] = []
    for (a, b), count in pair_counts.most_common():
        margins = pair_margins[(a, b)]
        avg_margin = sum(margins) / len(margins) if margins else 0.0
        verbatims = pair_verbatims[(a, b)][:max_verbatims]
        weak_pairs.append(
            {
                "pair": [a, b],
                "count": count,
                "avg_margin": round(avg_margin, 4),
                "verbatims": verbatims,
            }
        )

    # Generate structured advice for each pair (no count threshold — M1)
    advice: list[dict[str, Any]] = []
    for wp in weak_pairs:
        a, b = wp["pair"]
        count = wp["count"]
        verbatim_str = ""
        if wp["verbatims"]:
            examples = [f'"{v[:80]}"' for v in wp["verbatims"]]
            verbatim_str = f" Exemples a faible marge : {', '.join(examples)}."

        advice.append(
            {
                "type": "confused_pair",
                "pair": [a, b],
                "evidence": "margins",
                "n_exemples_faibles": count,
                "avg_margin": wp["avg_margin"],
                "suggestion": (
                    f"Les intentions '{a}' et '{b}' sont proches en marge "
                    f"({count} exemples avec ecart top1-top2 < {margin_threshold}, "
                    f"marge moyenne {wp['avg_margin']:.3f}). "
                    f"Ajoutez des exemples discriminants entre ces deux intentions."
                    f"{verbatim_str}"
                ),
                "verbatims": wp["verbatims"],
            }
        )

    return weak_pairs, advice


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
    dict with training results, optional evaluation, and phase profile.
    """
    results: dict[str, Any] = {"level1": {}, "level2": {}, "evaluation": None}
    profile: dict[str, float] = {}
    t_start = time.perf_counter()

    def _progress(step: str, detail: dict[str, Any] | None = None) -> None:
        if on_progress:
            on_progress(step, detail or {})

    # Read training hyperparameters from config (L2)
    tp = config.training

    # --- Level 1 ---
    _progress("l1_preparing")
    texts, labels = prepare_l1_training_data(config)

    if len(texts) == 0:
        results["level1"] = {"error": "No training data for L1"}
        return results

    _progress(
        "l1_training", {"num_samples": len(texts), "num_classes": len(set(labels))}
    )
    t_l1 = time.perf_counter()
    classifier = SetFitClassifier(config.bot_id, "level1")
    train_result = classifier.train(
        texts,
        labels,
        base_model=base_model,
        num_iterations=tp.num_iterations,
        num_epochs=tp.num_epochs,
        batch_size=tp.batch_size,
    )
    profile["l1_train_s"] = round(time.perf_counter() - t_l1, 2)
    results["level1"] = train_result

    # --- Evaluation L1 (L3: base-model CV + M1: structured advice) ---
    if run_evaluation and len(texts) >= 4:
        _progress("l1_evaluating")
        t_eval = time.perf_counter()
        eval_result = cross_validate(texts, labels, base_model=base_model)

        # M1: margin analysis on the trained model
        weak_pairs, margin_advice = compute_margin_analysis(classifier, texts, labels)

        # M1: merge CV + margin advice, deduplicate pairs, sort by severity
        merged = _merge_and_sort_advice(eval_result.advice, margin_advice)
        eval_result.advice = merged

        if weak_pairs:
            eval_result.extra_data["margin_weak_pairs"] = weak_pairs

        profile["eval_s"] = round(time.perf_counter() - t_eval, 2)
        results["evaluation"] = eval_result.to_dict()

    # --- Level 2 (per intent with sub-motifs) ---
    t_l2 = time.perf_counter()
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
        l2_result = l2_classifier.train(
            l2_texts,
            l2_labels,
            base_model=base_model,
            num_iterations=tp.num_iterations,
            num_epochs=tp.num_epochs,
            batch_size=tp.batch_size,
        )
        results["level2"][intent.id] = l2_result
    profile["l2_train_s"] = round(time.perf_counter() - t_l2, 2)

    # --- A4: Write manifest (atomic commit marker) ---
    _progress("writing_manifest")
    try:
        dataset_hash = compute_dataset_hash(texts, labels)

        levels: dict[str, LevelInfo] = {}

        l1_dir = get_model_dir(config.bot_id, "level1")
        levels["level1"] = LevelInfo(
            files=compute_file_hashes(l1_dir),
            labels=sorted(set(labels)),
            n_train_examples=len(texts),
        )

        for intent in config.intents:
            if intent.id in results.get("level2", {}) and "error" not in results[
                "level2"
            ].get(intent.id, {}):
                l2_dir = get_model_dir(config.bot_id, "level2", intent.id)
                l2_texts_i, l2_labels_i = prepare_l2_training_data(intent)
                levels[f"level2_{intent.id}"] = LevelInfo(
                    files=compute_file_hashes(l2_dir),
                    labels=sorted(set(l2_labels_i)),
                    n_train_examples=len(l2_texts_i),
                )

        # B3: Measure inference latency (L5: with warm-up + resource cleanup)
        latency: dict[str, Any] = {}
        try:
            t_lat = time.perf_counter()
            latency = measure_inference_latency(config.bot_id)
            profile["latency_measure_s"] = round(time.perf_counter() - t_lat, 2)
            results["inference_latency_ms"] = latency
            logger.info(
                "Inference latency for bot %s: P50=%.1fms, P95=%.1fms",
                config.bot_id,
                latency.get("p50", 0),
                latency.get("p95", 0),
            )
        except Exception:
            logger.warning("Could not measure inference latency", exc_info=True)

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

    profile["total_s"] = round(time.perf_counter() - t_start, 2)
    results["profile"] = profile
    logger.info("Training profile for bot %s: %s", config.bot_id, profile)

    _progress("done", results)
    return results
