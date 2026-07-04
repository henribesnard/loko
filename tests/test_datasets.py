"""C1 — Tests for frozen evaluation datasets.

Verifies invariants:
  - train/held-out intersection is empty
  - Exact row counts
  - SHA-256 hashes match HASHES.sha256
  - pieges.csv has exactly 15 cases T01-T15
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

DATASETS_DIR = Path(__file__).resolve().parent.parent / "eval" / "datasets"

_datasets_exist = (DATASETS_DIR / "train.csv").is_file()
_require_datasets = pytest.mark.skipif(
    not _datasets_exist,
    reason="eval/datasets/ not generated (run tools/make_datasets.py)",
)


def _read_texts(csv_path: Path) -> set[str]:
    """Read 'text' column from a CSV."""
    texts: set[str] = set()
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            texts.add(row["text"])
    return texts


def _count_rows(csv_path: Path) -> int:
    with open(csv_path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@_require_datasets
def test_train_heldout_disjoint():
    """Train and held-out sets must be disjoint (no data leakage)."""
    train_texts = _read_texts(DATASETS_DIR / "train.csv")
    heldout_texts = _read_texts(DATASETS_DIR / "heldout_metier.csv")
    overlap = train_texts & heldout_texts
    assert not overlap, f"Overlap found: {list(overlap)[:5]}"


@_require_datasets
def test_heldout_metier_count():
    assert _count_rows(DATASETS_DIR / "heldout_metier.csv") == 100


@_require_datasets
def test_heldout_conseiller_count():
    assert _count_rows(DATASETS_DIR / "heldout_conseiller.csv") == 126


@_require_datasets
def test_heldout_horsscope_count():
    assert _count_rows(DATASETS_DIR / "heldout_horsscope.csv") == 100


@_require_datasets
def test_pieges_count():
    assert _count_rows(DATASETS_DIR / "pieges.csv") == 15


@_require_datasets
def test_pieges_ids():
    """Each trap case should have a unique T01-T15 ID."""
    ids: list[str] = []
    with open(DATASETS_DIR / "pieges.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ids.append(row["id"])
    expected = [f"T{i:02d}" for i in range(1, 16)]
    assert sorted(ids) == expected


@_require_datasets
def test_hashes_match():
    """HASHES.sha256 must match actual file hashes."""
    hashes_path = DATASETS_DIR / "HASHES.sha256"
    assert hashes_path.is_file(), "HASHES.sha256 not found"

    for line in hashes_path.read_text(encoding="utf-8").strip().split("\n"):
        parts = line.split("  ", 1)
        assert len(parts) == 2, f"Invalid HASHES line: {line}"
        expected_hash, fname = parts
        actual = _sha256(DATASETS_DIR / fname)
        assert actual == expected_hash, f"Hash mismatch for {fname}"


@_require_datasets
def test_deterministic_regeneration():
    """Re-running make_datasets produces identical output (seed=42)."""
    from tools.make_datasets import generate_datasets

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(__file__).resolve().parent.parent / "dataset.csv"
        if not source.is_file():
            pytest.skip("dataset.csv not available")
        generate_datasets(source, Path(tmpdir))

        # Compare hashes
        for fname in ["train.csv", "heldout_metier.csv", "heldout_conseiller.csv",
                       "heldout_horsscope.csv", "pieges.csv"]:
            expected = _sha256(DATASETS_DIR / fname)
            actual = _sha256(Path(tmpdir) / fname)
            assert expected == actual, f"Regeneration produced different {fname}"
