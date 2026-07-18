#!/usr/bin/env python3
"""T1 — Triple version check: pyproject.toml, importlib, OpenAPI.

Exits non-zero on any divergence.

Usage:
    python tools/check_version_sync.py
    python tools/check_version_sync.py --against-tag v1.3.4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    pyproject = ROOT / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def read_importlib_version() -> str | None:
    """Read version via importlib.metadata (same as loko.__version__)."""
    try:
        from importlib.metadata import version

        return version("loko")
    except Exception:
        return None


def read_openapi_version(base_url: str = "http://127.0.0.1:8000") -> str | None:
    """Read version from running server's /api/openapi.json."""
    try:
        import httpx

        resp = httpx.get(f"{base_url}/api/openapi.json", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("info", {}).get("version")
    except Exception:
        return None


def read_git_tag() -> str:
    """Read the current exact tag from git describe."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T1 — Triple version check for LOKO releases"
    )
    parser.add_argument(
        "--against-tag",
        default=None,
        help="Expected git tag (e.g., v1.3.4). Checks tag is on HEAD and versions match.",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="Base URL for OpenAPI version check (default: skip if not provided)",
    )
    args = parser.parse_args()

    errors: list[str] = []
    checks: list[str] = []

    # 1. pyproject.toml version
    pyproject_version = read_pyproject_version()
    if not pyproject_version:
        errors.append("pyproject.toml: version not found")
    else:
        checks.append(f"pyproject.toml: {pyproject_version}")

    # 2. importlib version (if loko is installed)
    importlib_version = read_importlib_version()
    if importlib_version is not None:
        checks.append(f"importlib.metadata: {importlib_version}")
        if pyproject_version and importlib_version != pyproject_version:
            errors.append(
                f"importlib.metadata ({importlib_version}) != pyproject.toml ({pyproject_version})"
            )
    else:
        checks.append("importlib.metadata: loko not installed (skipped)")

    # 3. OpenAPI version (if server URL provided)
    if args.server_url:
        openapi_version = read_openapi_version(args.server_url)
        if openapi_version is not None:
            checks.append(f"OpenAPI info.version: {openapi_version}")
            if pyproject_version and openapi_version != pyproject_version:
                errors.append(
                    f"OpenAPI ({openapi_version}) != pyproject.toml ({pyproject_version})"
                )
        else:
            errors.append(f"OpenAPI: could not reach {args.server_url}/api/openapi.json")

    # 4. Git tag check (if --against-tag)
    if args.against_tag:
        git_tag = read_git_tag()
        expected_tag = args.against_tag
        expected_version = expected_tag.lstrip("v")

        checks.append(f"git tag on HEAD: {git_tag or '(none)'}")
        checks.append(f"expected tag: {expected_tag}")

        if not git_tag:
            errors.append(f"no git tag on HEAD (expected {expected_tag})")
        elif git_tag != expected_tag:
            errors.append(f"git tag ({git_tag}) != expected ({expected_tag})")

        if pyproject_version and pyproject_version != expected_version:
            errors.append(
                f"pyproject.toml ({pyproject_version}) != tag version ({expected_version})"
            )

    # Report
    print("=== LOKO Version Sync Check ===")
    for check in checks:
        print(f"  {check}")

    if errors:
        print(f"\nFAIL — {len(errors)} divergence(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\nPASS — all versions consistent")
        sys.exit(0)


if __name__ == "__main__":
    main()
