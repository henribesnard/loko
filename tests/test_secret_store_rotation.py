"""D3/C-V3 — Master key rotation tests.

Tests:
  - rotate re-encrypts all secrets
  - dry-run counts without modifying
  - rotation survives restart (new instance with new key)
  - rotation on empty store returns 0
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cryptography.fernet import Fernet

from loko.security.secret_store import SecretStore


@pytest.fixture
def store_with_secrets(tmp_path: Path, monkeypatch):
    """Create a SecretStore with 3 secrets and a known key."""
    key = Fernet.generate_key()
    monkeypatch.setenv("LOKO_SECRET_KEY", key.decode("utf-8"))

    db_path = tmp_path / "test_secrets.db"
    store = SecretStore(str(db_path))

    refs = []
    for plaintext in ["secret-alpha", "secret-beta", "secret-gamma"]:
        refs.append(store.put(plaintext))

    return store, db_path, key, refs


class TestSecretStoreRotation:
    """Tests for SecretStore.rotate() and the rotation CLI."""

    def test_rotate_reencrypts_all(self, store_with_secrets):
        """After rotation, all 3 secrets decrypt correctly with the new key."""
        store, db_path, old_key, refs = store_with_secrets
        new_key = Fernet.generate_key()

        count = store.rotate(new_key)
        assert count == 3

        # After rotate(), the store's internal fernet uses the new key
        assert store.get(refs[0]) == "secret-alpha"
        assert store.get(refs[1]) == "secret-beta"
        assert store.get(refs[2]) == "secret-gamma"

    def test_rotate_restart_survival(self, store_with_secrets, monkeypatch):
        """Rotation survives destroy + re-instantiate with new key."""
        store, db_path, old_key, refs = store_with_secrets
        new_key = Fernet.generate_key()

        store.rotate(new_key)

        # Destroy old store instance
        del store

        # Re-instantiate with new key
        monkeypatch.setenv("LOKO_SECRET_KEY", new_key.decode("utf-8"))
        new_store = SecretStore(str(db_path))

        assert new_store.get(refs[0]) == "secret-alpha"
        assert new_store.get(refs[1]) == "secret-beta"
        assert new_store.get(refs[2]) == "secret-gamma"

    def test_rotate_empty_store(self, tmp_path: Path, monkeypatch):
        """Rotation on empty store returns 0."""
        key = Fernet.generate_key()
        monkeypatch.setenv("LOKO_SECRET_KEY", key.decode("utf-8"))

        db_path = tmp_path / "empty_secrets.db"
        store = SecretStore(str(db_path))

        new_key = Fernet.generate_key()
        count = store.rotate(new_key)
        assert count == 0

    def test_old_key_cannot_decrypt_after_rotation(self, store_with_secrets, monkeypatch):
        """After rotation, old key no longer decrypts the secrets."""
        store, db_path, old_key, refs = store_with_secrets
        new_key = Fernet.generate_key()

        store.rotate(new_key)
        del store

        # Try to read with old key — should fail
        monkeypatch.setenv("LOKO_SECRET_KEY", old_key.decode("utf-8"))
        old_store = SecretStore(str(db_path))

        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            old_store.get(refs[0])


class TestRotationCLI:
    """Tests for the rotation CLI entry point."""

    def test_dry_run(self, store_with_secrets, monkeypatch, capsys):
        """--dry-run counts secrets without modifying."""
        store, db_path, old_key, refs = store_with_secrets

        from loko.security.rotate_master_key import main

        exit_code = main(["--db-path", str(db_path), "--dry-run"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Would rotate 3" in captured.out

        # Verify secrets unchanged: still readable with old key
        assert store.get(refs[0]) == "secret-alpha"

    def test_rotate_with_journal(self, store_with_secrets, tmp_path, monkeypatch):
        """Rotation writes a valid JSON journal."""
        store, db_path, old_key, refs = store_with_secrets
        journal_path = tmp_path / "journal.json"

        from loko.security.rotate_master_key import main

        exit_code = main([
            "--db-path", str(db_path),
            "--journal", str(journal_path),
        ])
        assert exit_code == 0

        import json
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        assert journal["rotated"] == 3
        assert journal["verified"] == 3
        assert "key_fingerprint" in journal
        assert len(journal["key_fingerprint"]) == 8

    def test_missing_db(self, tmp_path, monkeypatch):
        """Non-existent DB path returns error code."""
        monkeypatch.setenv("LOKO_SECRET_KEY", Fernet.generate_key().decode("utf-8"))

        from loko.security.rotate_master_key import main

        exit_code = main(["--db-path", str(tmp_path / "nonexistent.db")])
        assert exit_code == 1
