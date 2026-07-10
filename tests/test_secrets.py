"""
Tests for secrets management (K1)
Implements tests for PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
"""

import os
import tempfile
from pathlib import Path
import pytest

from loko.config.secrets import (
    get_secret,
    get_secret_bytes,
    verify_secret_file_permissions,
)


class TestGetSecret:
    """Test get_secret() function."""

    def test_get_secret_from_file(self, tmp_path):
        """Test reading secret from file."""
        secret_file = tmp_path / "test_secret.txt"
        secret_file.write_text("secret-value-from-file\n")

        with patch_env({"TEST_SECRET_FILE": str(secret_file)}):
            value = get_secret("TEST_SECRET")
            assert value == "secret-value-from-file"

    def test_get_secret_from_env(self):
        """Test reading secret from environment variable."""
        with patch_env({"TEST_SECRET": "secret-value-from-env"}):
            value = get_secret("TEST_SECRET")
            assert value == "secret-value-from-env"

    def test_get_secret_file_priority_over_env(self, tmp_path):
        """Test that _FILE variant takes priority over env var."""
        secret_file = tmp_path / "test_secret.txt"
        secret_file.write_text("file-value")

        with patch_env({
            "TEST_SECRET": "env-value",
            "TEST_SECRET_FILE": str(secret_file),
        }):
            value = get_secret("TEST_SECRET")
            assert value == "file-value"

    def test_get_secret_strips_whitespace(self, tmp_path):
        """Test that secret values are stripped of whitespace."""
        secret_file = tmp_path / "test_secret.txt"
        secret_file.write_text("  secret-with-spaces  \n\n")

        with patch_env({"TEST_SECRET_FILE": str(secret_file)}):
            value = get_secret("TEST_SECRET")
            assert value == "secret-with-spaces"

    def test_get_secret_not_found_required(self):
        """Test that required secrets raise ValueError if not found."""
        with patch_env({}):
            with pytest.raises(ValueError, match="Required secret 'MISSING_SECRET' not found"):
                get_secret("MISSING_SECRET", required=True)

    def test_get_secret_not_found_optional(self):
        """Test that optional secrets return None if not found."""
        with patch_env({}):
            value = get_secret("MISSING_SECRET", required=False)
            assert value is None

    def test_get_secret_not_found_with_default(self):
        """Test that default value is returned if secret not found."""
        with patch_env({}):
            value = get_secret("MISSING_SECRET", default="default-value")
            assert value == "default-value"

    def test_get_secret_file_not_found(self):
        """Test that non-existent file falls back to env var."""
        with patch_env({
            "TEST_SECRET": "fallback-value",
            "TEST_SECRET_FILE": "/nonexistent/file.txt",
        }):
            value = get_secret("TEST_SECRET")
            assert value == "fallback-value"

    def test_get_secret_empty_file(self, tmp_path):
        """Test that empty file falls back to env var."""
        secret_file = tmp_path / "empty.txt"
        secret_file.write_text("")

        with patch_env({
            "TEST_SECRET": "fallback-value",
            "TEST_SECRET_FILE": str(secret_file),
        }):
            value = get_secret("TEST_SECRET")
            assert value == "fallback-value"


class TestGetSecretBytes:
    """Test get_secret_bytes() function."""

    def test_get_secret_bytes_from_file(self, tmp_path):
        """Test reading binary secret from file."""
        secret_file = tmp_path / "binary_secret.bin"
        secret_file.write_bytes(b"\x00\x01\x02\x03")

        with patch_env({"TEST_SECRET_FILE": str(secret_file)}):
            value = get_secret_bytes("TEST_SECRET")
            assert value == b"\x00\x01\x02\x03"

    def test_get_secret_bytes_from_env(self):
        """Test reading binary secret from env (as UTF-8)."""
        with patch_env({"TEST_SECRET": "test-value"}):
            value = get_secret_bytes("TEST_SECRET")
            assert value == b"test-value"


class TestVerifySecretFilePermissions:
    """Test verify_secret_file_permissions() function."""

    def test_verify_permissions_600(self, tmp_path):
        """Test that 600 permissions are accepted."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("secret")
        secret_file.chmod(0o600)

        assert verify_secret_file_permissions(str(secret_file)) is True

    def test_verify_permissions_400(self, tmp_path):
        """Test that 400 permissions are accepted."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("secret")
        secret_file.chmod(0o400)

        assert verify_secret_file_permissions(str(secret_file)) is True

    def test_verify_permissions_644_insecure(self, tmp_path):
        """Test that 644 permissions are rejected."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("secret")
        secret_file.chmod(0o644)

        # Should return False for insecure permissions
        assert verify_secret_file_permissions(str(secret_file)) is False

    def test_verify_nonexistent_file(self):
        """Test that non-existent file returns False."""
        assert verify_secret_file_permissions("/nonexistent/file.txt") is False


# Helper context manager for patching environment
class patch_env:
    """Context manager to temporarily patch environment variables."""

    def __init__(self, env_dict):
        self.env_dict = env_dict
        self.original_env = {}

    def __enter__(self):
        # Save original values
        for key in self.env_dict:
            if key in os.environ:
                self.original_env[key] = os.environ[key]

        # Clear any *_FILE variants
        for key in list(os.environ.keys()):
            if key.endswith("_FILE") or key in self.env_dict:
                if key not in self.original_env:
                    self.original_env[key] = None

        # Set new values
        for key, value in self.env_dict.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        return self

    def __exit__(self, *args):
        # Restore original values
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        # Clean up any keys we set that weren't there before
        for key in self.env_dict:
            if key not in self.original_env:
                os.environ.pop(key, None)
