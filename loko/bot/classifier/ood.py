"""E2 — Out-of-Distribution (OOD) rejection for hors_perimetre.

Replaces the learned hors_perimetre class with a novelty score
based on cosine distance to the nearest class centroid in the
embedding space.

Principle:
    d(x) = 1 - max_c cos(embed(x), centroid_c)
    d(x) >= seuil_ood  =>  REJECT (hors_perimetre)
    d(x) <  seuil_ood  =>  pass to softmax 8-class classifier

Invariants:
    - 100% deterministic, no LLM.
    - Centroids are computed at training time and frozen in the manifest.
    - Threshold is calibrated on train.csv only (never held-out).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Filename for persisted centroids alongside the model
CENTROIDS_FILENAME = "ood_centroids.json"


def compute_centroids(
    embeddings: list[list[float]],
    labels: list[str],
) -> dict[str, list[float]]:
    """Compute the L2-normalized centroid for each class.

    Parameters
    ----------
    embeddings : list of float vectors
        One embedding per training example (already normalized or not).
    labels : list[str]
        Corresponding class labels.

    Returns
    -------
    dict mapping class_id -> centroid (L2-normalized).
    """
    from collections import defaultdict

    accum: dict[str, list[list[float]]] = defaultdict(list)
    for emb, label in zip(embeddings, labels):
        accum[label].append(emb)

    centroids: dict[str, list[float]] = {}
    for cls_id, vecs in sorted(accum.items()):
        dim = len(vecs[0])
        mean = [0.0] * dim
        for v in vecs:
            for i in range(dim):
                mean[i] += v[i]
        n = len(vecs)
        mean = [m / n for m in mean]

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in mean))
        if norm > 0:
            mean = [x / norm for x in mean]

        centroids[cls_id] = mean

    return centroids


def ood_score(
    embedding: list[float],
    centroids: dict[str, list[float]],
) -> float:
    """Compute the OOD novelty score for a single embedding.

    Returns d(x) = 1 - max_c cos(x, centroid_c).
    Range: [0, 2] in theory; [0, 1] in practice for normalized vectors.
    Higher = more OOD.
    """
    # L2-normalize the input embedding
    norm = math.sqrt(sum(x * x for x in embedding))
    if norm > 0:
        embedding = [x / norm for x in embedding]

    max_cos = -1.0
    for centroid in centroids.values():
        cos_sim = sum(a * b for a, b in zip(embedding, centroid))
        if cos_sim > max_cos:
            max_cos = cos_sim

    return 1.0 - max_cos


def calibrate_ood_threshold(
    in_embeddings: list[list[float]],
    out_embeddings: list[list[float]],
    centroids: dict[str, list[float]],
    *,
    n_steps: int = 100,
) -> tuple[float, dict[str, Any]]:
    """Calibrate seuil_ood by maximizing binary F1 on train data.

    Parameters
    ----------
    in_embeddings : list
        Embeddings of in-distribution examples (business classes).
    out_embeddings : list
        Embeddings of declared hors_perimetre examples (used as
        negative validation set, NOT as training class).
    centroids : dict
        Pre-computed class centroids.
    n_steps : int
        Number of threshold candidates to evaluate.

    Returns
    -------
    (best_threshold, calibration_info)
    """
    # Compute OOD scores for both sets
    in_scores = [ood_score(e, centroids) for e in in_embeddings]
    out_scores = [ood_score(e, centroids) for e in out_embeddings]

    if not in_scores or not out_scores:
        # Fallback: no calibration possible
        return 0.5, {
            "method": "default",
            "n_in": len(in_scores),
            "n_out": len(out_scores),
        }

    # Score range
    all_scores = in_scores + out_scores
    s_min = min(all_scores)
    s_max = max(all_scores)

    best_f1 = -1.0
    best_t = (s_min + s_max) / 2

    step = (s_max - s_min) / n_steps if n_steps > 0 else 0.01
    t = s_min
    while t <= s_max + 1e-9:
        # in-distribution should be BELOW threshold (not OOD)
        # out-distribution should be ABOVE threshold (OOD)
        tp = sum(1 for s in out_scores if s >= t)  # correctly rejected
        fp = sum(1 for s in in_scores if s >= t)  # falsely rejected
        fn = sum(1 for s in out_scores if s < t)  # missed OOD

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        if f1 > best_f1:
            best_f1 = f1
            best_t = t

        t += step

    return round(best_t, 6), {
        "method": "f1_maximization_train_only",
        "n_in": len(in_scores),
        "n_out": len(out_scores),
        "best_f1": round(best_f1, 4),
        "in_score_range": [round(min(in_scores), 4), round(max(in_scores), 4)],
        "out_score_range": [round(min(out_scores), 4), round(max(out_scores), 4)],
    }


def save_centroids(centroids: dict[str, list[float]], model_dir: Path) -> str:
    """Persist centroids to disk and return their SHA-256 hash."""
    path = model_dir / CENTROIDS_FILENAME
    content = json.dumps(centroids, ensure_ascii=False, sort_keys=True)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_centroids(model_dir: Path) -> dict[str, list[float]] | None:
    """Load centroids from disk, or None if not present."""
    path = model_dir / CENTROIDS_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load OOD centroids from %s", path)
        return None
