#!/usr/bin/env python3
"""
O5: Audit residual constants outside config
Implements PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Searches for hardcoded constants that should be in configuration.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Constants that are OK (not decision-related)
ALLOWED_CONSTANTS = {
    # HTTP status codes
    200, 201, 204, 400, 401, 403, 404, 429, 500, 503,
    # Common sizes
    1024, 2048, 4096,
    # Time constants
    60, 3600, 86400,  # seconds in minute/hour/day
    24,  # hours in day
    7,  # days in week
    # Common limits
    100, 1000,
}

# Decision-related constants that should be in config (red flag)
DECISION_CONSTANTS = {
    0.7, 0.5, 0.8, 0.9,  # Common threshold values
}

# Paths to exclude
EXCLUDE_PATHS = {
    "tests/", "node_modules/", ".git/", "__pycache__/",
    "build/", "dist/", ".venv/", "venv/",
}


def should_exclude(path: Path) -> bool:
    """Check if path should be excluded."""
    path_str = str(path)
    return any(excl in path_str for excl in EXCLUDE_PATHS)


def find_numeric_constants(file_path: Path) -> List[Tuple[int, str, float]]:
    """
    Find numeric constants in a Python file.

    Returns:
        List of (line_number, line_content, constant_value)
    """
    results = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return results

    for line_num, line in enumerate(content.split("\n"), 1):
        # Skip comments
        if line.strip().startswith("#"):
            continue

        # Find floating point numbers (potential thresholds)
        floats = re.findall(r"\b(\d+\.\d+)\b", line)
        for f in floats:
            value = float(f)
            # Flag decision-related constants
            if value in DECISION_CONSTANTS or (0.0 < value < 1.0 and value != 0.5):
                results.append((line_num, line.strip(), value))

        # Find integers (potential limits, sizes)
        integers = re.findall(r"\b(\d+)\b", line)
        for i in integers:
            value = int(i)
            # Only flag if not in allowed list and not too small/large
            if value not in ALLOWED_CONSTANTS and 10 <= value <= 10000:
                results.append((line_num, line.strip(), float(value)))

    return results


def audit_directory(root_dir: Path) -> dict:
    """
    Audit a directory for hardcoded constants.

    Returns:
        Dict of {file_path: [(line_num, line, value), ...]}
    """
    findings = {}

    for py_file in root_dir.rglob("*.py"):
        if should_exclude(py_file):
            continue

        constants = find_numeric_constants(py_file)
        if constants:
            findings[py_file] = constants

    return findings


def main():
    """Run constants audit."""
    print("=" * 80)
    print("O5: Audit of Residual Constants")
    print("=" * 80)
    print()

    # Audit loko/ directory
    loko_dir = Path("loko")
    if not loko_dir.exists():
        print(f"Error: {loko_dir} not found")
        sys.exit(1)

    print(f"Auditing {loko_dir}...")
    print()

    findings = audit_directory(loko_dir)

    if not findings:
        print("✅ No suspicious constants found!")
        return

    # Report findings
    print(f"Found constants in {len(findings)} files:")
    print()

    decision_related = []
    other_constants = []

    for file_path, constants in sorted(findings.items()):
        for line_num, line, value in constants:
            if value in DECISION_CONSTANTS or (0.0 < value < 1.0):
                decision_related.append((file_path, line_num, line, value))
            else:
                other_constants.append((file_path, line_num, line, value))

    # Report decision-related constants (red flag)
    if decision_related:
        print("🔴 DECISION-RELATED CONSTANTS (should be in config):")
        print()
        for file_path, line_num, line, value in decision_related:
            rel_path = file_path.relative_to(loko_dir.parent)
            print(f"  {rel_path}:{line_num}")
            print(f"    Value: {value}")
            print(f"    Line: {line}")
            print()

    # Report other constants (review recommended)
    if other_constants:
        print("⚠️  OTHER CONSTANTS (review recommended):")
        print()
        for file_path, line_num, line, value in other_constants[:20]:  # Limit output
            rel_path = file_path.relative_to(loko_dir.parent)
            print(f"  {rel_path}:{line_num}")
            print(f"    Value: {value}")
            print(f"    Line: {line[:80]}")
            print()

        if len(other_constants) > 20:
            print(f"  ... and {len(other_constants) - 20} more")
            print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Decision-related constants: {len(decision_related)}")
    print(f"Other constants: {len(other_constants)}")
    print()

    if decision_related:
        print("⚠️  Action required: Move decision constants to BotConfig journey")
        sys.exit(1)
    else:
        print("✅ No decision constants found outside config")


if __name__ == "__main__":
    main()
