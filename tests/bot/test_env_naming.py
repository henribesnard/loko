"""N3 — Anti-regression: RAGKIT_* env vars must only be read via get_env().

Tests:
- LOKO_ENV is read correctly
- RAGKIT_ENV fallback works with DeprecationWarning
- LOKO_* takes precedence over RAGKIT_*
- No direct os.environ["RAGKIT_*"] reads outside config/env.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# get_env() behavior tests
# ---------------------------------------------------------------------------

def test_loko_env_read(monkeypatch):
    """LOKO_ENV=test is read correctly by get_env()."""
    monkeypatch.setenv("LOKO_ENV", "test")
    monkeypatch.delenv("RAGKIT_ENV", raising=False)

    from loko.config.env import get_env
    assert get_env("ENV") == "test"


def test_ragkit_fallback_with_warning(monkeypatch):
    """RAGKIT_ENV fallback works and emits DeprecationWarning."""
    monkeypatch.delenv("LOKO_ENV", raising=False)
    monkeypatch.setenv("RAGKIT_ENV", "test")

    from loko.config.env import get_env
    with pytest.warns(DeprecationWarning, match="RAGKIT_ENV is deprecated"):
        val = get_env("ENV")
    assert val == "test"


def test_loko_takes_precedence(monkeypatch):
    """When both LOKO_ and RAGKIT_ are set, LOKO_ wins."""
    monkeypatch.setenv("LOKO_MODE", "server")
    monkeypatch.setenv("RAGKIT_MODE", "desktop")

    from loko.config.env import get_env
    assert get_env("MODE") == "server"


def test_default_when_neither_set(monkeypatch):
    """When neither is set, the default is returned."""
    monkeypatch.delenv("LOKO_MODE", raising=False)
    monkeypatch.delenv("RAGKIT_MODE", raising=False)

    from loko.config.env import get_env
    assert get_env("MODE", "desktop") == "desktop"
    assert get_env("MODE") is None


# ---------------------------------------------------------------------------
# Lint guard: no direct RAGKIT_ reads outside config/env.py
# ---------------------------------------------------------------------------

_LOKO_ROOT = Path(__file__).resolve().parent.parent.parent / "loko"

# Patterns that indicate direct os.environ reads of RAGKIT_ variables
_FORBIDDEN = [
    re.compile(r'os\.environ\s*\[\s*["\']RAGKIT_'),
    re.compile(r'os\.environ\.get\s*\(\s*["\']RAGKIT_'),
    re.compile(r'os\.getenv\s*\(\s*["\']RAGKIT_'),
]

_ALLOWED_FILE = _LOKO_ROOT / "config" / "env.py"


def test_no_direct_ragkit_reads():
    """No module in loko/ (except config/env.py) should read RAGKIT_* directly.

    All reads must go through get_env() for backward-compat handling.
    """
    violations = []
    for py_file in _LOKO_ROOT.rglob("*.py"):
        if py_file == _ALLOWED_FILE:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            for pattern in _FORBIDDEN:
                if pattern.search(line):
                    rel = py_file.relative_to(_LOKO_ROOT.parent)
                    violations.append(f"  {rel}:{i}: {line.strip()}")

    assert not violations, (
        "Direct os.environ reads of RAGKIT_* found outside config/env.py:\n"
        + "\n".join(violations)
        + "\n\nUse `from loko.config.env import get_env` instead."
    )
