"""S1-1 — Separability measurement tool.

Computes intrinsic separability metrics for a LOKO bot classifier:
  - F1 / precision / recall per class (cross-validation on frozen embeddings)
  - Full confusion matrix
  - Top1-top2 margin distribution with percentiles
  - Inter-centroid pairwise cosine distances
  - Intra-class radius (max distance to centroid per class)
  - Per-class: 5 closest examples to a foreign centroid
  - Example count per class vs floor (8)

Usage:
    python tools/measure_separability.py --bot-dir <path> [--out <dir>]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _l2_normalize(v: list[float]) -> list[float]:
    """L2-normalize a vector."""
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0:
        return v
    return [x / norm for x in v]


def _percentiles(values: list[float], ps: list[int]) -> dict[str, float]:
    """Compute percentiles from a sorted list of values."""
    if not values:
        return {f"P{p}": 0.0 for p in ps}
    s = sorted(values)
    n = len(s)
    result = {}
    for p in ps:
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        result[f"P{p}"] = s[lo] * (1 - frac) + s[hi] * frac
    return result


def measure_separability(
    bot_dir: Path,
    *,
    k: int = 5,
    n_seeds: int = 3,
    min_examples_floor: int = 8,
    n_closest_foreign: int = 5,
) -> dict:
    """Run all separability measurements for a bot.

    Parameters
    ----------
    bot_dir : Path
        Path to the bot directory containing config.json.
    k : int
        Number of folds for cross-validation.
    n_seeds : int
        Number of random seeds for CV averaging.
    min_examples_floor : int
        Minimum examples per class (warning threshold).
    n_closest_foreign : int
        Number of closest-to-foreign-centroid examples to report per class.

    Returns
    -------
    dict
        Full separability report as a JSON-serializable dict.
    """
    from loko.bot.classifier.ood import compute_centroids
    from loko.bot.classifier.setfit_service import (
        DEFAULT_BASE_MODEL,
        prepare_l1_training_data,
        resolve_base_model,
    )
    from loko.bot.classifier.training import cross_validate
    from loko.bot.models import BotConfig

    t0 = time.perf_counter()

    # --- Load config ---
    config_path = bot_dir / "config.json"
    if not config_path.is_file():
        print(f"Error: No config found at {config_path}", file=sys.stderr)
        sys.exit(1)

    config = BotConfig.model_validate_json(config_path.read_text(encoding="utf-8"))

    # --- Prepare training data ---
    texts, labels = prepare_l1_training_data(config)
    unique_labels = sorted(set(labels))
    class_counts = defaultdict(int)
    for lbl in labels:
        class_counts[lbl] += 1

    # --- Class count vs floor ---
    class_count_report = {}
    for lbl in unique_labels:
        cnt = class_counts[lbl]
        class_count_report[lbl] = {
            "count": cnt,
            "above_floor": cnt >= min_examples_floor,
        }
    below_floor = [lbl for lbl, info in class_count_report.items() if not info["above_floor"]]

    print(f"Loaded {len(texts)} examples across {len(unique_labels)} classes")
    if below_floor:
        print(f"  WARNING: classes below floor ({min_examples_floor}): {below_floor}")

    # --- Cross-validation ---
    print(f"Running {k}-fold CV with {n_seeds} seeds on frozen base model...")
    cv_result = cross_validate(texts, labels, base_model=DEFAULT_BASE_MODEL, k=k, n_seeds=n_seeds)
    print(f"  CV accuracy: {cv_result.accuracy:.1%}")
    print(f"  CV duration: {cv_result.duration_s:.1f}s")

    # --- Compute embeddings for centroid analysis ---
    print("Encoding embeddings for centroid analysis...")
    from sentence_transformers import SentenceTransformer

    resolved = resolve_base_model(DEFAULT_BASE_MODEL)
    encoder = SentenceTransformer(resolved)
    embeddings_np = encoder.encode(texts, show_progress_bar=False)
    del encoder

    embeddings = [list(map(float, e)) for e in embeddings_np]

    # --- Compute centroids ---
    centroids = compute_centroids(embeddings, labels)

    # --- Inter-centroid pairwise cosine distances ---
    centroid_labels = sorted(centroids.keys())
    pairwise_distances = {}
    for i, a in enumerate(centroid_labels):
        for b in centroid_labels[i + 1:]:
            cos_sim = _cosine_similarity(centroids[a], centroids[b])
            dist = 1.0 - cos_sim
            pairwise_distances[f"{a} <-> {b}"] = round(dist, 6)

    # Sorted by distance ascending (closest pairs first = most confused)
    pairwise_sorted = dict(sorted(pairwise_distances.items(), key=lambda x: x[1]))

    # --- Intra-class radius (max distance to own centroid per class) ---
    intra_class = defaultdict(list)
    for emb, lbl in zip(embeddings, labels):
        cos_sim = _cosine_similarity(emb, centroids[lbl])
        intra_class[lbl].append(1.0 - cos_sim)

    intra_class_radius = {}
    intra_class_stats = {}
    for lbl in unique_labels:
        dists = intra_class[lbl]
        intra_class_radius[lbl] = round(max(dists), 6) if dists else 0.0
        intra_class_stats[lbl] = {
            "max_dist": round(max(dists), 6) if dists else 0.0,
            "mean_dist": round(sum(dists) / len(dists), 6) if dists else 0.0,
            "n": len(dists),
        }

    # --- Per-class: closest examples to a foreign centroid ---
    closest_foreign = {}
    for lbl in unique_labels:
        # For each example of this class, find min distance to any foreign centroid
        foreign_centroids = {k: v for k, v in centroids.items() if k != lbl}
        if not foreign_centroids:
            closest_foreign[lbl] = []
            continue

        scored = []
        class_indices = [i for i, l in enumerate(labels) if l == lbl]
        for idx in class_indices:
            emb = embeddings[idx]
            # Find closest foreign centroid
            best_foreign_lbl = None
            best_cos = -1.0
            for flbl, fcentroid in foreign_centroids.items():
                cos_sim = _cosine_similarity(emb, fcentroid)
                if cos_sim > best_cos:
                    best_cos = cos_sim
                    best_foreign_lbl = flbl
            scored.append({
                "text": texts[idx],
                "closest_foreign_class": best_foreign_lbl,
                "cosine_to_foreign": round(best_cos, 4),
                "cosine_to_own": round(_cosine_similarity(emb, centroids[lbl]), 4),
            })

        # Sort by cosine_to_foreign descending (closest to foreign = most risky)
        scored.sort(key=lambda x: x["cosine_to_foreign"], reverse=True)
        closest_foreign[lbl] = scored[:n_closest_foreign]

    # --- Margin distribution (on frozen embeddings via logistic head) ---
    # Reuse CV to get per-example margins. We do a single pass with seed=42.
    print("Computing margin distribution...")
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    emb_array = np.array(embeddings_np)
    y = np.array([label_to_idx[l] for l in labels])

    # Full-data logistic regression (for margin measurement, not evaluation)
    lr = LogisticRegression(max_iter=500, solver="lbfgs", multi_class="multinomial")
    lr.fit(emb_array, y)
    proba = lr.predict_proba(emb_array)

    margins = []
    per_class_margins = defaultdict(list)
    for i in range(len(texts)):
        sorted_p = sorted(proba[i], reverse=True)
        margin = float(sorted_p[0] - sorted_p[1]) if len(sorted_p) >= 2 else 1.0
        margins.append(margin)
        per_class_margins[labels[i]].append(margin)

    margin_percentiles = _percentiles(margins, [10, 25, 50, 75, 90])
    per_class_margin_percentiles = {}
    for lbl in unique_labels:
        per_class_margin_percentiles[lbl] = _percentiles(
            per_class_margins[lbl], [10, 25, 50, 75, 90]
        )

    duration_s = time.perf_counter() - t0

    # --- Assemble report ---
    report = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bot_id": config.bot_id,
        "bot_name": config.name,
        "base_model": DEFAULT_BASE_MODEL,
        "n_examples": len(texts),
        "n_classes": len(unique_labels),
        "classes": unique_labels,
        "duration_s": round(duration_s, 1),
        "class_counts": {lbl: class_counts[lbl] for lbl in unique_labels},
        "min_examples_floor": min_examples_floor,
        "classes_below_floor": below_floor,
        "cross_validation": {
            "k": k,
            "n_seeds": n_seeds,
            "accuracy": round(cv_result.accuracy, 4),
            "per_class_f1": {k: round(v, 4) for k, v in cv_result.per_class_f1.items()},
            "confusion_matrix": cv_result.confusion_matrix,
            "class_names": cv_result.class_names,
            "advice": cv_result.advice,
        },
        "centroids": {
            "inter_centroid_distances": pairwise_sorted,
            "intra_class_stats": intra_class_stats,
        },
        "margins": {
            "global_percentiles": {k: round(v, 4) for k, v in margin_percentiles.items()},
            "per_class_percentiles": {
                lbl: {k: round(v, 4) for k, v in pctls.items()}
                for lbl, pctls in per_class_margin_percentiles.items()
            },
        },
        "closest_to_foreign_centroid": closest_foreign,
    }

    return report


def _print_summary(report: dict) -> None:
    """Print human-readable summary to stdout."""
    print(f"\n{'=' * 60}")
    print(f"SEPARABILITY REPORT — {report['bot_name']} ({report['bot_id']})")
    print(f"{'=' * 60}")
    print(f"  Examples: {report['n_examples']}  |  Classes: {report['n_classes']}  |  Duration: {report['duration_s']}s")

    if report["classes_below_floor"]:
        print(f"  WARNING: {len(report['classes_below_floor'])} class(es) below floor ({report['min_examples_floor']}): {report['classes_below_floor']}")

    cv = report["cross_validation"]
    print(f"\n--- Cross-validation ({cv['k']}-fold, {cv['n_seeds']} seeds) ---")
    print(f"  Overall accuracy: {cv['accuracy']:.1%}")
    print("  Per-class F1:")
    for cls, f1 in sorted(cv["per_class_f1"].items(), key=lambda x: x[1]):
        count = report["class_counts"][cls]
        flag = " <<<" if f1 < 0.70 else ""
        print(f"    {cls:30s}  F1={f1:.3f}  (n={count}){flag}")

    margins = report["margins"]
    print("\n--- Margin distribution (top1 - top2) ---")
    gp = margins["global_percentiles"]
    print(f"  Global: P10={gp['P10']:.3f}  P25={gp['P25']:.3f}  P50={gp['P50']:.3f}  P75={gp['P75']:.3f}  P90={gp['P90']:.3f}")

    centroids = report["centroids"]
    print("\n--- Inter-centroid distances (closest pairs) ---")
    for pair, dist in list(centroids["inter_centroid_distances"].items())[:5]:
        flag = " <<<" if dist < 0.10 else ""
        print(f"  {pair:45s}  d={dist:.4f}{flag}")
    n_pairs = len(centroids["inter_centroid_distances"])
    if n_pairs > 5:
        print(f"  ... and {n_pairs - 5} more pairs")

    print("\n--- Intra-class radius (max dist to own centroid) ---")
    for cls in sorted(centroids["intra_class_stats"].keys()):
        stats = centroids["intra_class_stats"][cls]
        print(f"  {cls:30s}  max={stats['max_dist']:.4f}  mean={stats['mean_dist']:.4f}")

    print("\n--- Closest to foreign centroid (per class, top examples) ---")
    for cls in sorted(report["closest_to_foreign_centroid"].keys()):
        examples = report["closest_to_foreign_centroid"][cls]
        if not examples:
            continue
        print(f"  [{cls}]")
        for ex in examples:
            print(f"    cos_foreign={ex['cosine_to_foreign']:.3f} ({ex['closest_foreign_class']})  cos_own={ex['cosine_to_own']:.3f}  \"{ex['text'][:60]}\"")

    print(f"\n{'=' * 60}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S1-1 — Measure intrinsic separability of a LOKO bot classifier",
    )
    parser.add_argument(
        "--bot-dir",
        type=Path,
        required=True,
        help="Path to the bot directory (contains config.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for the JSON report (default: stdout only)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of CV folds (default: 5)",
    )
    parser.add_argument(
        "--n-seeds",
        type=int,
        default=3,
        help="Number of CV seeds for averaging (default: 3)",
    )

    args = parser.parse_args(argv)

    report = measure_separability(args.bot_dir, k=args.k, n_seeds=args.n_seeds)
    _print_summary(report)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        out_file = args.out / "separability_report.json"
        out_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nReport written to {out_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
