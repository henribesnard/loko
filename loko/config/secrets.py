"""
Secrets management for LOKO
Implements K1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Supports reading secrets from:
1. Docker secrets files (/run/secrets/*)
2. Custom secret files (via *_FILE env vars)
3. Environment variables (fallback for dev/desktop)

Usage:
    from loko.config.secrets import get_secret

    admin_token = get_secret("LOKO_ADMIN_TOKEN")
    # Looks for:
    # 1. /run/secrets/loko_admin_token (if LOKO_ADMIN_TOKEN_FILE is set)
    # 2. LOKO_ADMIN_TOKEN env var
    # 3. Raises ValueError if not found and required=True
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_secret(
    env_var_name: str,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    """
    Get a secret value from Docker secrets or environment variables.

    Args:
        env_var_name: Name of the environment variable (e.g., "LOKO_ADMIN_TOKEN")
        required: If True, raise ValueError if secret not found
        default: Default value if secret not found and not required

    Returns:
        Secret value as string, or None/default if not found

    Raises:
        ValueError: If required=True and secret not found
    """
    # 1. Check for _FILE variant (Docker secrets or custom file path)
    file_var_name = f"{env_var_name}_FILE"
    secret_file_path = os.getenv(file_var_name)

    if secret_file_path:
        secret_path = Path(secret_file_path)
        if secret_path.exists() and secret_path.is_file():
            try:
                # Read secret from file, strip whitespace
                with open(secret_path, "r", encoding="utf-8") as f:
                    secret_value = f.read().strip()

                if secret_value:
                    return secret_value
            except (IOError, PermissionError) as e:
                # Log error but continue to fallback
                logger.warning("Could not read secret file %s: %s", secret_path, e)

    # 2. Fallback to environment variable
    secret_value = os.getenv(env_var_name)
    if secret_value:
        return secret_value

    # 3. Not found
    if required:
        raise ValueError(
            f"Required secret '{env_var_name}' not found. "
            f"Set {env_var_name} or {file_var_name} (pointing to a file)."
        )

    return default


def get_secret_bytes(
    env_var_name: str,
    required: bool = False,
    default: bytes | None = None,
) -> bytes | None:
    """
    Get a secret value as bytes (for binary secrets like keys).

    Args:
        env_var_name: Name of the environment variable
        required: If True, raise ValueError if secret not found
        default: Default value if secret not found and not required

    Returns:
        Secret value as bytes, or None/default if not found
    """
    file_var_name = f"{env_var_name}_FILE"
    secret_file_path = os.getenv(file_var_name)

    if secret_file_path:
        secret_path = Path(secret_file_path)
        if secret_path.exists() and secret_path.is_file():
            try:
                with open(secret_path, "rb") as f:
                    return f.read()
            except (IOError, PermissionError) as e:
                logger.warning("Could not read secret file %s: %s", secret_path, e)

    # Fallback to environment variable (decode from string)
    secret_value = os.getenv(env_var_name)
    if secret_value:
        return secret_value.encode("utf-8")

    if required:
        raise ValueError(
            f"Required secret '{env_var_name}' not found. "
            f"Set {env_var_name} or {file_var_name} (pointing to a file)."
        )

    return default


def verify_secret_file_permissions(secret_file_path: str) -> bool:
    """
    Verify that a secret file has secure permissions (600 or more restrictive).

    Args:
        secret_file_path: Path to the secret file

    Returns:
        True if permissions are secure, False otherwise
    """
    try:
        secret_path = Path(secret_file_path)
        if not secret_path.exists():
            return False

        # Get file permissions
        stat_info = secret_path.stat()
        mode = stat_info.st_mode & 0o777

        # Secret files should be 600 (owner read/write only) or more restrictive
        # Allow 600 (0o600) or 400 (0o400)
        if mode in (0o600, 0o400):
            return True

        logger.warning(
            "Secret file %s has insecure permissions: %s. Recommended: chmod 600",
            secret_path, oct(mode),
        )
        return False

    except Exception as e:
        logger.warning("Could not check permissions for %s: %s", secret_file_path, e)
        return False
