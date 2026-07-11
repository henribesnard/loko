"""H4 + V1 — Repository hygiene guards.

CI tests ensuring:
- No sensitive data committed under data/ (H4)
- Version consistency across pyproject.toml, loko/__init__.py, main.py (V1)
- eval/datasets/ integrity (V2)
"""

from __future__ import annotations

import json
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
    ".json",
    ".csv",
    ".md",
    ".txt",
    ".sha256",
    ".safetensors",
    ".pkl",
    ".bin",
    ".onnx",  # model binaries (gitignored)
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
        re.compile(r"logger\.\w+\(.*,\s*\w*token\b", re.IGNORECASE),
        re.compile(r"logger\.\w+\(.*,\s*\w*password\b", re.IGNORECASE),
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

    assert not violations, "Potential secret leaks in log statements:\n" + "\n".join(
        f"  {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# V1 — Version consistency
# ---------------------------------------------------------------------------


def _read_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    pyproject = REPO_ROOT / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            # version = "0.3.7"
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError("version not found in pyproject.toml")


def test_version_consistency():
    """V1: pyproject.toml, loko.__version__, and main.py FastAPI version must match."""
    pyproject_version = _read_pyproject_version()

    # loko.__version__
    from loko import __version__

    assert __version__ == pyproject_version, (
        f"loko.__version__={__version__!r} != pyproject.toml={pyproject_version!r}"
    )

    # main.py FastAPI version (read from app instance)
    import sys

    # Avoid side effects from existing imports
    if "loko.main" in sys.modules:
        del sys.modules["loko.main"]
    from loko.main import create_app

    app = create_app()
    assert app.version == pyproject_version, (
        f"FastAPI app.version={app.version!r} != pyproject.toml={pyproject_version!r}"
    )


def test_openapi_version():
    """V1: openapi_w2.json version must match pyproject.toml."""
    openapi_path = REPO_ROOT / "openapi_w2.json"
    if not openapi_path.exists():
        pytest.skip("openapi_w2.json not present")

    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    openapi_version = spec.get("info", {}).get("version", "")
    pyproject_version = _read_pyproject_version()

    assert openapi_version == pyproject_version, (
        f"openapi_w2.json version={openapi_version!r} != pyproject.toml={pyproject_version!r}"
    )


# ---------------------------------------------------------------------------
# V2 — eval/datasets/ integrity — REMOVED (client-specific)
# ---------------------------------------------------------------------------
# The frozen datasets were specific to a client case study and have been purged.
# Generic evaluation tools remain in loko/eval/.
