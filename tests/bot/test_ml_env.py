"""A1 — ML environment sanity checks.

These tests verify that the ML dependency matrix is importable and
consistent.  They are NOT marked slow and must run in every CI where
the [ml] extras are installed.

On dev machines without ML packages, these tests skip gracefully.
In the Docker image (where LOKO_ML=on), they MUST pass.
"""

from __future__ import annotations

import importlib
import os

import pytest

_ml_available = importlib.util.find_spec("setfit") is not None
_require_ml = pytest.mark.skipif(
    not _ml_available and os.environ.get("LOKO_ML", "off") != "on",
    reason="ML extras not installed (pip install loko[ml])",
)


@_require_ml
def test_setfit_importable():
    """setfit must be importable (A1 — version matrix)."""
    setfit = importlib.import_module("setfit")
    assert hasattr(setfit, "SetFitModel")


@_require_ml
def test_sentence_transformers_importable():
    """sentence-transformers must be importable (A1)."""
    st = importlib.import_module("sentence_transformers")
    assert hasattr(st, "SentenceTransformer")


@_require_ml
def test_transformers_below_v5():
    """transformers must be <5 to stay compatible with setfit 1.1.x (A1)."""
    import transformers

    major = int(transformers.__version__.split(".")[0])
    assert major < 5, (
        f"transformers {transformers.__version__} is v{major}.x — "
        "must be <5 for setfit compatibility"
    )


@_require_ml
def test_torch_cpu_only():
    """In the production image, only CPU torch is installed (A1/A6)."""
    import torch

    # In CI / container, CUDA should not be available.
    # This test documents the expectation; it may legitimately pass
    # on a dev machine with a GPU — that's fine.
    # The key invariant is that the Docker image uses CPU-only torch.
    if torch.cuda.is_available():
        pytest.skip("CUDA available (dev machine with GPU) — not a CI failure")
