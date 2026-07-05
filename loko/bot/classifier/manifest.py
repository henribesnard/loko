"""LOKO Bot — Model manifest for integrity verification (A4).

The manifest is written at the end of training as an atomic commit
marker.  A model directory without a valid manifest is considered
incomplete/corrupt.

verify_model() checks:
  (a) manifest present + schema valid
  (b) SHA-256 of each file matches
  (c) model loads successfully
  (d) smoke test: predictions return valid labels
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loko.bot.classifier.model_store import get_model_dir
from loko.bot.session_store import get_bot_dir

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

# Canary verbatims for smoke test (one per family)
SMOKE_VERBATIMS = [
    "Je voudrais connaitre le montant de ma cotisation",          # métier
    "Je veux parler à un conseiller",                              # transverse
    "Raconte-moi une blague",                                      # hors-scope
]


@dataclass
class LevelInfo:
    """Manifest info for one classification level."""
    files: dict[str, str]       # filename -> sha256
    labels: list[str]
    n_train_examples: int


@dataclass
class ModelVerification:
    """Result of verify_model()."""
    ok: bool
    errors: list[str] = field(default_factory=list)

    @property
    def error_code(self) -> str | None:
        """Return a short error code for the first error, or None."""
        if not self.errors:
            return None
        first = self.errors[0].lower()
        if "manifest" in first and ("missing" in first or "not found" in first):
            return "manifest_missing"
        if "manifest" in first and ("invalid" in first or "schema" in first or "json" in first):
            return "manifest_invalid"
        if "hash" in first:
            return "hash_mismatch"
        if "load" in first:
            return "load_error"
        if "smoke" in first:
            return "smoke_failed"
        if "retrain" in first:
            return "retrain_required"
        return "verification_error"


def compute_file_hashes(directory: Path) -> dict[str, str]:
    """Compute SHA-256 for every file in *directory* (non-recursive for model files)."""
    hashes: dict[str, str] = {}
    if not directory.is_dir():
        return hashes
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.name != MANIFEST_FILENAME:
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            hashes[f.name] = h
    return hashes


def compute_dataset_hash(texts: list[str], labels: list[str]) -> str:
    """Deterministic hash of the training data (order-sensitive)."""
    h = hashlib.sha256()
    for t, l in zip(texts, labels):
        h.update(f"{t}\t{l}\n".encode("utf-8"))
    return h.hexdigest()


def get_manifest_path(bot_id: str) -> Path:
    """Return the path to the model manifest for a bot."""
    return get_bot_dir(bot_id) / "models" / MANIFEST_FILENAME


def manifest_exists(bot_id: str) -> bool:
    """Check if a manifest exists for the bot."""
    return get_manifest_path(bot_id).is_file()


def write_manifest(
    bot_id: str,
    levels: dict[str, LevelInfo],
    dataset_hash: str,
    train_metrics: dict[str, Any] | None = None,
    inference_latency_ms: dict[str, float] | None = None,
) -> Path:
    """Write the model manifest after successful training.

    This must be called LAST — a missing manifest means training
    was incomplete.
    """
    manifest = {
        "schema": MANIFEST_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bot_id": bot_id,
        "levels": {},
        "dataset_hash": dataset_hash,
        "train_metrics": train_metrics or {},
        "inference_latency_ms": inference_latency_ms or {},
    }

    for level_name, info in levels.items():
        manifest["levels"][level_name] = {
            "files": info.files,
            "labels": info.labels,
            "n_train_examples": info.n_train_examples,
        }

    path = get_manifest_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote model manifest for bot %s at %s", bot_id, path)
    return path


def read_manifest(bot_id: str) -> dict[str, Any] | None:
    """Read and parse the manifest, or None if missing/invalid."""
    path = get_manifest_path(bot_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def verify_model(bot_id: str) -> ModelVerification:
    """Full model verification (A4/A5).

    Checks:
      (a) manifest present + valid schema
      (b) SHA-256 of each file matches manifest
      (c) model loads successfully via SetFit
      (d) smoke test: inference returns valid labels
    """
    errors: list[str] = []

    # (a) Manifest presence and schema
    path = get_manifest_path(bot_id)
    if not path.is_file():
        return ModelVerification(ok=False, errors=["Manifest not found"])
    manifest = read_manifest(bot_id)
    if manifest is None:
        return ModelVerification(ok=False, errors=["Manifest invalid JSON or unreadable"])

    if manifest.get("schema") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"Manifest schema {manifest.get('schema')} != expected {MANIFEST_SCHEMA_VERSION}"
        )
        return ModelVerification(ok=False, errors=errors)

    levels = manifest.get("levels", {})
    if "level1" not in levels:
        errors.append("Manifest missing level1 entry")
        return ModelVerification(ok=False, errors=errors)

    # (b) Hash verification for each level
    for level_name, level_data in levels.items():
        expected_files = level_data.get("files", {})
        intent_id = None
        if level_name.startswith("level2_"):
            intent_id = level_name[len("level2_"):]
            model_dir = get_model_dir(bot_id, "level2", intent_id)
        else:
            model_dir = get_model_dir(bot_id, level_name)

        if not model_dir.is_dir():
            errors.append(f"Model directory missing for {level_name}")
            continue

        actual_hashes = compute_file_hashes(model_dir)
        for fname, expected_hash in expected_files.items():
            actual = actual_hashes.get(fname)
            if actual is None:
                errors.append(f"File {fname} missing in {level_name}")
            elif actual != expected_hash:
                errors.append(
                    f"Hash mismatch for {level_name}/{fname}: "
                    f"expected {expected_hash[:12]}… got {actual[:12]}…"
                )

    if errors:
        return ModelVerification(ok=False, errors=errors)

    # (c) Model loading
    try:
        from loko.bot.classifier.setfit_service import SetFitClassifier

        clf = SetFitClassifier(bot_id, "level1")
        if not clf.load():
            errors.append("Failed to load level1 model from disk")
            return ModelVerification(ok=False, errors=errors)
    except ImportError:
        errors.append("SetFit not installed — cannot verify model loading")
        return ModelVerification(ok=False, errors=errors)
    except Exception as exc:
        errors.append(f"Load error: {exc}")
        return ModelVerification(ok=False, errors=errors)

    # (d) Smoke test
    expected_labels = set(levels["level1"].get("labels", []))
    if not expected_labels:
        errors.append("Smoke test: no labels in manifest")
        return ModelVerification(ok=False, errors=errors)

    for verbatim in SMOKE_VERBATIMS:
        try:
            scores = clf.classify(verbatim, top_k=1)
            if not scores:
                errors.append(f"Smoke test: no prediction for '{verbatim[:40]}…'")
                continue
            predicted_label = scores[0][0]
            if predicted_label not in expected_labels:
                errors.append(
                    f"Smoke test: predicted '{predicted_label}' not in manifest labels"
                )
        except Exception as exc:
            errors.append(f"Smoke test error on '{verbatim[:40]}…': {exc}")

    if errors:
        return ModelVerification(ok=False, errors=errors)

    return ModelVerification(ok=True)


_WARMUP_RUNS = 10
_MEASURE_RUNS = 100


def measure_inference_latency(
    bot_id: str,
    n_warmup: int = _WARMUP_RUNS,
    n_samples: int = _MEASURE_RUNS,
) -> dict[str, Any]:
    """Measure P50/P95 inference latency on the L1 classifier (B3/L5).

    Methodology (aligned with independent counter-measure):
      1. Free training resources (GC, reset BLAS threads to runtime value)
      2. Warm-up: ``n_warmup`` inferences not counted (cache priming)
      3. Measure: ``n_samples`` inferences timed individually
      4. Report P50/P95 in milliseconds + methodology metadata

    Returns dict with keys: p50, p95, methodology.
    Raises if the model cannot be loaded.
    """
    import gc

    from loko.bot.classifier.setfit_service import SetFitClassifier

    # --- Step 0: free training resources ---
    gc.collect()

    try:
        import torch
        # Reset thread count to a sensible runtime value (training may have
        # bumped it).  Default to physical core count or 4.
        import os
        runtime_threads = int(os.environ.get("LOKO_INFERENCE_THREADS", "4"))
        torch.set_num_threads(runtime_threads)
    except ImportError:
        pass  # No torch — ONNX runtime or similar

    # --- Load model ---
    clf = SetFitClassifier(bot_id, "level1")
    if not clf.load():
        raise RuntimeError(f"Cannot measure latency: model not loaded for bot {bot_id}")

    # Use smoke verbatims in rotation for realistic diversity
    all_texts = [SMOKE_VERBATIMS[i % len(SMOKE_VERBATIMS)] for i in range(n_warmup + n_samples)]

    # --- Step 1: warm-up (not counted) ---
    for text in all_texts[:n_warmup]:
        clf.classify(text, top_k=5)

    # --- Step 2: measured inferences ---
    latencies: list[float] = []
    for text in all_texts[n_warmup:]:
        start = time.perf_counter()
        clf.classify(text, top_k=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    latencies.sort()
    p50_idx = int(len(latencies) * 0.50)
    p95_idx = int(len(latencies) * 0.95)

    return {
        "p50": round(latencies[p50_idx], 2),
        "p95": round(latencies[min(p95_idx, len(latencies) - 1)], 2),
        "methodology": {
            "warmup": n_warmup,
            "measured": n_samples,
            "gc_before": True,
            "threads_reset": True,
        },
    }
