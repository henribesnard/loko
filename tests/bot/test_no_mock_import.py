"""C7 — Lint test: production code must not import or define mock classes.

Rules (C7.2):
1. No module under loko/ (excluding loko/testing/) imports mock classes at
   module level.
2. No module under loko/ (excluding loko/testing/) defines a class named
   Mock*, _Mock*, or InMemorySearchBackend.
3. No module under loko/ (excluding loko/testing/) imports loko.testing.mocks
   at module level.
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


def _is_testing_module(filepath: Path) -> bool:
    """Return True if filepath is inside loko/testing/."""
    try:
        filepath.relative_to(LOKO_ROOT / "testing")
        return True
    except ValueError:
        return False


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
            # Check for import of loko.testing.mocks module itself
            if node.module and "loko.testing.mocks" in node.module:
                found.append(f"import from {node.module}")
        # import loko.testing.mocks
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "loko.testing.mocks" in alias.name:
                    found.append(f"import {alias.name}")
    return found


def _find_mock_class_definitions(filepath: Path) -> list[str]:
    """Return Mock*/InMemorySearchBackend class definitions in *filepath*."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            name = node.name
            if name in MOCK_CLASS_NAMES or name.startswith("Mock") or name.startswith("_Mock"):
                found.append(name)
    return found


def test_no_mock_import_at_module_level():
    """No module under loko/ (excluding loko/testing/) should import mock
    classes at module level.
    """
    violations: list[str] = []

    for root, _dirs, files in os.walk(LOKO_ROOT):
        filepath_root = Path(root)
        # Skip test directories and loko/testing/
        if "test" in filepath_root.name.lower():
            continue
        if _is_testing_module(filepath_root):
            continue

        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = filepath_root / fname
            if _is_testing_module(filepath):
                continue
            found = _find_module_level_imports(filepath)
            if found:
                rel_path = filepath.relative_to(LOKO_ROOT.parent)
                violations.append(f"{rel_path}: {', '.join(found)}")

    assert not violations, (
        "Production code imports mock classes at module level (C7):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_no_mock_class_definitions():
    """No module under loko/ (excluding loko/testing/) should define
    mock classes.
    """
    violations: list[str] = []

    for root, _dirs, files in os.walk(LOKO_ROOT):
        filepath_root = Path(root)
        if "test" in filepath_root.name.lower():
            continue
        if _is_testing_module(filepath_root):
            continue

        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = filepath_root / fname
            if _is_testing_module(filepath):
                continue
            found = _find_mock_class_definitions(filepath)
            if found:
                rel_path = filepath.relative_to(LOKO_ROOT.parent)
                violations.append(f"{rel_path}: defines {', '.join(found)}")

    assert not violations, (
        "Production code defines mock classes (C7):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
