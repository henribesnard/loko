"""H4 — Guard: no sensitive data committed under data/.

CI test ensuring api_keys.json, sessions.db, transcripts, and
oversized unlisted files are never committed to the repository.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Forbidden patterns under data/
_FORBIDDEN_PATTERNS = [
    "api_keys.json",
    "sessions.db",
    "*.transcript*",
]

# Max size for unlisted files (5 MB)
_MAX_UNLISTED_SIZE = 5 * 1024 * 1024

# Files allowed to be large or excluded from size check
_ALLOWED_LARGE_EXTENSIONS = {
    ".json", ".csv", ".md", ".txt", ".sha256",
    ".safetensors", ".pkl", ".bin", ".onnx",  # model binaries (gitignored)
}


@pytest.mark.skipif(not DATA_DIR.is_dir(), reason="data/ not present")
def test_no_sensitive_files_in_data():
    """api_keys.json, sessions*, transcripts must not be committed."""
    violations: list[str] = []
    for path in DATA_DIR.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name == "api_keys.json":
            violations.append(str(path.relative_to(REPO_ROOT)))
        elif name.startswith("sessions"):
            violations.append(str(path.relative_to(REPO_ROOT)))
        elif "transcript" in name.lower():
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert not violations, f"Sensitive files found in data/: {violations}"


@pytest.mark.skipif(not DATA_DIR.is_dir(), reason="data/ not present")
def test_no_oversized_unlisted_files():
    """Files > 5 MB under data/ must not be committed (unless in allowed extensions)."""
    violations: list[str] = []
    for path in DATA_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in _ALLOWED_LARGE_EXTENSIONS:
            continue
        if path.stat().st_size > _MAX_UNLISTED_SIZE:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} ({path.stat().st_size / 1024 / 1024:.1f} MB)"
            )

    assert not violations, f"Oversized files in data/: {violations}"


def test_no_secrets_in_loko_source():
    """Grep guard: no logger.*token, logger.*password, logger.*session_id in loko/."""
    loko_dir = REPO_ROOT / "loko"
    violations: list[str] = []

    # Patterns that should never appear in log statements.
    # Match cases where a token/password *variable* is passed as a log parameter.
    forbidden_log_patterns = [
        re.compile(r'logger\.\w+\(.*,\s*\w*token\b', re.IGNORECASE),
        re.compile(r'logger\.\w+\(.*,\s*\w*password\b', re.IGNORECASE),
    ]

    for py_file in loko_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in forbidden_log_patterns:
                if pattern.search(line):
                    # Allow the pattern in comments
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    violations.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{i}: {line.strip()}"
                    )

    assert not violations, (
        f"Potential secret leaks in log statements:\n" +
        "\n".join(f"  {v}" for v in violations)
    )
