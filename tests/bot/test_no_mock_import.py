"""A3 — Lint test: production code must not import mock classes at module level.

Mocks are only allowed inside test code or behind RAGKIT_ENV guards.
This test ensures no production module (loko/) directly imports the 4
mock classes at module scope.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

LOKO_ROOT = Path(__file__).resolve().parent.parent.parent / "loko"

# Classes whose *module-level* import in production code is forbidden.
MOCK_CLASS_NAMES = {
    "_MockClassifier",
    "MockLLMProvider",
    "InMemorySearchBackend",
    "MockEscalationProvider",
}


def _find_module_level_imports(filepath: Path) -> list[str]:
    """Return mock class names imported at module level in *filepath*."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    found: list[str] = []
    for node in ast.iter_child_nodes(tree):
        # from x import Y, Z
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name in MOCK_CLASS_NAMES:
                    found.append(name)
    return found


def test_no_mock_import_at_module_level():
    """No module under loko/ (excluding tests/) should import mock classes
    at module level.  Conditional imports inside functions are OK because
    they are guarded by RAGKIT_ENV or is_test checks.
    """
    violations: list[str] = []

    for root, _dirs, files in os.walk(LOKO_ROOT):
        # Skip test directories
        rel = os.path.relpath(root, LOKO_ROOT)
        if "test" in rel.lower():
            continue

        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = Path(root) / fname
            found = _find_module_level_imports(filepath)
            if found:
                rel_path = filepath.relative_to(LOKO_ROOT.parent)
                violations.append(f"{rel_path}: {', '.join(found)}")

    assert not violations, (
        "Production code imports mock classes at module level (A3/GNG-10):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
