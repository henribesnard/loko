"""
Tests for API key rotation (K3)
Implements tests for PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
"""

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import json

from loko.api.api_keys import (
    generate_api_key,
    validate_api_key_for_bot,
    rotate_api_key,
    cleanup_expired_keys,
    list_api_keys,
    _load_keys,
    _save_keys,
)


@pytest.fixture
def temp_bots_dir(monkeypatch):
    """Create temporary bots directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bots_dir = Path(tmpdir) / "bots"
        bots_dir.mkdir()

        # Monkey patch get_bots_dir
        monkeypatch.setattr("loko.api.api_keys.get_bots_dir", lambda: bots_dir)
        monkeypatch.setattr("loko.bot.session_store.get_bots_dir", lambda: bots_dir)

        yield bots_dir


class TestAPIKeyRotation:
    """Test API key rotation functionality."""

    def test_rotate_api_key_basic(self, temp_bots_dir):
        """Test basic key rotation."""
        bot_id = "test-bot"

        # Create initial key
        old_raw_key, old_key_id = generate_api_key(bot_id, label="Original")

        # Verify old key works
        record = validate_api_key_for_bot(old_raw_key, bot_id)
        assert record is not None
        assert record.key_id == old_key_id

        # Rotate
        result = rotate_api_key(bot_id, old_key_id, grace_period_hours=24)
        assert result is not None

        new_raw_key, new_key_id = result
        assert new_key_id != old_key_id
        assert new_raw_key != old_raw_key

        # Both keys should work during grace period
        old_record = validate_api_key_for_bot(old_raw_key, bot_id)
        assert old_record is not None
        assert old_record.expires_at is not None
        assert old_record.superseded_by == new_key_id

        new_record = validate_api_key_for_bot(new_raw_key, bot_id)
        assert new_record is not None
        assert new_record.expires_at is None  # New key doesn't expire

    def test_rotate_inherits_origins(self, temp_bots_dir):
        """Test that rotated key inherits allowed_origins."""
        bot_id = "test-bot"
        origins = ["https://example.com", "https://app.example.com"]

        # Create key with specific origins
        old_raw_key, old_key_id = generate_api_key(
            bot_id, label="With Origins", allowed_origins=origins
        )

        # Rotate
        new_raw_key, new_key_id = rotate_api_key(bot_id, old_key_id)
        assert new_raw_key is not None

        # New key should have same origins
        new_record = validate_api_key_for_bot(new_raw_key, bot_id)
        assert new_record.allowed_origins == origins

    def test_rotate_nonexistent_key(self, temp_bots_dir):
        """Test rotating a nonexistent key returns None."""
        bot_id = "test-bot"

        result = rotate_api_key(bot_id, "nonexistent-key-id")
        assert result is None

    def test_old_key_expires_after_grace_period(self, temp_bots_dir):
        """Test that old key expires after grace period."""
        bot_id = "test-bot"

        # Create and rotate
        old_raw_key, old_key_id = generate_api_key(bot_id)
        new_raw_key, new_key_id = rotate_api_key(bot_id, old_key_id, grace_period_hours=0)

        # Set expires_at to past (simulate expiration)
        keys = _load_keys(bot_id)
        for k in keys:
            if k.key_id == old_key_id:
                k.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                break
        _save_keys(bot_id, keys)

        # Old key should no longer validate
        old_record = validate_api_key_for_bot(old_raw_key, bot_id)
        assert old_record is None

        # New key should still work
        new_record = validate_api_key_for_bot(new_raw_key, bot_id)
        assert new_record is not None

    def test_cleanup_expired_keys(self, temp_bots_dir):
        """Test cleanup of expired keys."""
        bot_id = "test-bot"

        # Create and rotate multiple keys
        key1, id1 = generate_api_key(bot_id, label="Key1")
        key2, id2 = rotate_api_key(bot_id, id1, grace_period_hours=0)[0:2]
        key3, id3 = rotate_api_key(bot_id, id2, grace_period_hours=0)[0:2]

        # Set first two keys as expired
        keys = _load_keys(bot_id)
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        for k in keys:
            if k.key_id in [id1, id2]:
                k.expires_at = expired_time
        _save_keys(bot_id, keys)

        # Should have 3 keys before cleanup
        assert len(_load_keys(bot_id)) == 3

        # Cleanup
        deleted = cleanup_expired_keys(bot_id)
        assert deleted == 2

        # Should have 1 key left
        remaining_keys = _load_keys(bot_id)
        assert len(remaining_keys) == 1
        assert remaining_keys[0].key_id == id3

    def test_list_api_keys_shows_expiration(self, temp_bots_dir):
        """Test that list_api_keys includes expiration info."""
        bot_id = "test-bot"

        # Create and rotate
        old_raw_key, old_key_id = generate_api_key(bot_id, label="Old")
        new_raw_key, new_key_id = rotate_api_key(bot_id, old_key_id)

        # List keys
        keys_list = list_api_keys(bot_id)
        assert len(keys_list) == 2

        # Find old key
        old_key_info = next(k for k in keys_list if k["key_id"] == old_key_id)
        assert old_key_info["expires_at"] is not None
        assert old_key_info["superseded_by"] == new_key_id
        assert old_key_info["is_expired"] is False

        # Find new key
        new_key_info = next(k for k in keys_list if k["key_id"] == new_key_id)
        assert new_key_info["expires_at"] is None
        assert new_key_info["superseded_by"] is None

    def test_multiple_bots_cleanup(self, temp_bots_dir):
        """Test cleanup across multiple bots."""
        bot1 = "bot-1"
        bot2 = "bot-2"

        # Create expired keys in both bots
        key1, id1 = generate_api_key(bot1)
        key2, id2 = generate_api_key(bot2)

        # Expire both
        for bot_id, key_id in [(bot1, id1), (bot2, id2)]:
            keys = _load_keys(bot_id)
            for k in keys:
                if k.key_id == key_id:
                    k.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            _save_keys(bot_id, keys)

        # Cleanup all bots
        deleted = cleanup_expired_keys(bot_id=None)
        assert deleted == 2

    def test_scoping_non_regression(self, temp_bots_dir):
        """Test that rotation preserves bot scoping (non-regression test for lot T)."""
        bot1 = "bot-1"
        bot2 = "bot-2"

        # Create keys for two different bots
        key1, id1 = generate_api_key(bot1, label="Bot1 Key")
        key2, id2 = generate_api_key(bot2, label="Bot2 Key")

        # Rotate bot1's key
        new_key1, new_id1 = rotate_api_key(bot1, id1)

        # Old key1 should still only work for bot1 (not bot2)
        assert validate_api_key_for_bot(key1, bot1) is not None
        assert validate_api_key_for_bot(key1, bot2) is None

        # New key1 should only work for bot1
        assert validate_api_key_for_bot(new_key1, bot1) is not None
        assert validate_api_key_for_bot(new_key1, bot2) is None

        # Bot2's key should be unaffected
        assert validate_api_key_for_bot(key2, bot2) is not None
        assert validate_api_key_for_bot(key2, bot1) is None
