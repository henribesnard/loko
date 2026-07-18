"""M1 — Temperature scaling calibration for SetFit classifiers.

Temperature scaling adjusts the sharpness of softmax probabilities
without changing the ranking order. T < 1 sharpens (more confident),
T > 1 flattens (more uncertain).

Usage:
    from loko.bot.classifier.calibration import apply_temperature_scaling

    scaled = apply_temperature_scaling(scores, temperature=1.5)
"""

from __future__ import annotations

import math


def apply_temperature_scaling(
    scores: list[tuple[str, float]],
    temperature: float = 1.0,
) -> list[tuple[str, float]]:
    """Apply temperature scaling to softmax probabilities.

    Args:
        scores: List of (class_id, probability) pairs from classifier.
        temperature: Scaling factor. 1.0 = no change, <1 = sharper, >1 = flatter.

    Returns:
        Re-scaled and re-sorted (class_id, probability) pairs.
    """
    if temperature == 1.0 or not scores:
        return scores

    # Convert probabilities back to log-space
    eps = 1e-10
    logits = [math.log(max(p, eps)) for _, p in scores]
    ids = [id_ for id_, _ in scores]

    # Scale logits by temperature
    scaled_logits = [l / temperature for l in logits]

    # Re-apply softmax (with numerical stability)
    max_logit = max(scaled_logits)
    exp_vals = [math.exp(l - max_logit) for l in scaled_logits]
    sum_exp = sum(exp_vals)
    scaled_probs = [e / sum_exp for e in exp_vals]

    # Re-sort by probability (descending)
    result = sorted(
        zip(ids, scaled_probs),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(id_, float(p)) for id_, p in result]


def find_optimal_temperature(
    scored_samples: list[tuple[list[tuple[str, float]], str]],
    t_range: tuple[float, float, float] = (0.5, 3.0, 0.1),
) -> tuple[float, float]:
    """Find the temperature that minimizes Expected Calibration Error.

    Args:
        scored_samples: List of (classifier_scores, true_label) pairs.
        t_range: (min, max, step) for temperature search.

    Returns:
        (best_temperature, best_ece)
    """
    best_t = 1.0
    best_ece = float("inf")

    t_min, t_max, t_step = t_range
    t = t_min
    while t <= t_max + 1e-9:
        ece = _compute_ece(scored_samples, t)
        if ece < best_ece:
            best_ece = ece
            best_t = t
        t += t_step

    return round(best_t, 2), round(best_ece, 4)


def _compute_ece(
    scored_samples: list[tuple[list[tuple[str, float]], str]],
    temperature: float,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error with given temperature."""
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]

    for scores, true_label in scored_samples:
        scaled = apply_temperature_scaling(scores, temperature)
        if not scaled:
            continue
        top_id, top_prob = scaled[0]
        correct = top_id == true_label
        bin_idx = min(int(top_prob * n_bins), n_bins - 1)
        bins[bin_idx].append((top_prob, correct))

    total = sum(len(b) for b in bins)
    if total == 0:
        return 0.0

    ece = 0.0
    for bin_items in bins:
        if not bin_items:
            continue
        avg_conf = sum(p for p, _ in bin_items) / len(bin_items)
        avg_acc = sum(1.0 for _, c in bin_items if c) / len(bin_items)
        ece += len(bin_items) / total * abs(avg_conf - avg_acc)

    return ece
