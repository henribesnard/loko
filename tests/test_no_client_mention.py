"""Anti-regression guard: No client-specific mentions allowed in codebase.

This test ensures that no references to specific client names remain in the
codebase (code, tests, tools, frontend, configuration files).

Allowed exceptions:
- This guard file itself
- Git history (.git/)
- Build artifacts (node_modules/, __pycache__, dist/, build/)
- Client dataset (dataset.csv, already .gitignored)
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan
SCAN_DIRS = [
    REPO_ROOT / "loko",
    REPO_ROOT / "tests",
    REPO_ROOT / "tools",
    REPO_ROOT / "desktop" / "src",
    REPO_ROOT / "widget",
]

# Files to exclude (this guard itself + ignorable files)
EXCLUDE_PATTERNS = [
    "test_no_client_mention.py",  # This file
    "dataset.csv",  # Client data (gitignored)
    ".gitignore",
]


def test_no_client_mention_in_codebase():
    """Scan codebase for any mention of specific client names (case-insensitive)."""
    violations: list[str] = []
    search_term = "m" + "gen"  # Avoid self-match

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue

        for file_path in scan_dir.rglob("*"):
            # Skip directories
            if file_path.is_dir():
                continue

            # Skip excluded patterns
            if any(pattern in str(file_path) for pattern in EXCLUDE_PATTERNS):
                continue

            # Skip binary files and build artifacts
            if file_path.suffix in {
                ".pyc",
                ".so",
                ".dll",
                ".exe",
                ".bin",
                ".safetensors",
                ".pkl",
            }:
                continue
            if any(
                part in file_path.parts
                for part in {"__pycache__", "node_modules", "dist", "build", ".git"}
            ):
                continue

            # Scan text files
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if search_term.lower() in content.lower():
                    # Find line numbers for better reporting
                    lines_with_match = [
                        (i + 1, line.strip())
                        for i, line in enumerate(content.splitlines())
                        if search_term.lower() in line.lower()
                    ]
                    for line_num, line_text in lines_with_match:
                        violations.append(
                            f"{file_path.relative_to(REPO_ROOT)}:{line_num}: {line_text[:80]}"
                        )
            except Exception:
                # Skip files that can't be read as text
                continue

    if violations:
        violation_list = "\n".join(
            f"  - {v}" for v in violations[:20]
        )  # Limit to first 20
        if len(violations) > 20:
            violation_list += f"\n  ... and {len(violations) - 20} more"

        pytest.fail(
            f"Found {len(violations)} client-specific mention(s) in codebase:\n{violation_list}\n\n"
            f"Client names must not appear in the codebase. "
            f"Use neutral/generic terms instead."
        )


# Optional warning for domain-specific intent names (non-blocking)
DOMAIN_INTENT_NAMES = [
    "arret_travail",  # Sick leave (French labor domain)
    "cotisations",  # Contributions (French insurance)
    "teletransmission_noemie",  # Noemie transmission (French health system)
    "resiliation",  # Cancellation (French insurance)
    "justificatif_droits",  # Rights certificate (French admin)
    "changement_coordonnees",  # Contact change (French)
    "services_en_ligne",  # Online services (French)
]


def test_warn_domain_specific_intents_in_product_code():
    """Warn (don't fail) if domain-specific intent names appear in product code loko/**."""
    warnings: list[str] = []
    loko_dir = REPO_ROOT / "loko"

    if not loko_dir.exists():
        pytest.skip("loko/ directory not found")

    for file_path in loko_dir.rglob("*.py"):
        if file_path.is_dir():
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for intent_name in DOMAIN_INTENT_NAMES:
                if intent_name in content:
                    warnings.append(
                        f"{file_path.relative_to(REPO_ROOT)}: contains domain-specific intent '{intent_name}'"
                    )
        except Exception:
            continue

    if warnings:
        # This is a warning, not a failure - domain intent names are OK in tests/fixtures
        # but should NOT be hardcoded in product code
        warning_msg = "\n".join(f"  - {w}" for w in warnings)
        pytest.skip(
            f"⚠️  WARNING: Domain-specific intent names found in product code loko/**:\n{warning_msg}\n\n"
            f"These reveal the client sector. Product code should not hardcode client-specific intent names."
        )
