"""Tests for the API key management system."""

from __future__ import annotations


from loko.api.api_keys import (
    APIKeyRecord,
    check_origin,
    generate_api_key,
    list_api_keys,
    revoke_api_key,
    validate_api_key_for_bot,
)


class TestAPIKeys:
    def test_generate_and_validate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        raw_key, key_id = generate_api_key("bot-1", label="Test key")

        assert raw_key.startswith("loko_")
        assert key_id

        record = validate_api_key_for_bot(raw_key, "bot-1")
        assert record is not None
        assert record.bot_id == "bot-1"
        assert record.label == "Test key"

    def test_invalid_key_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        assert validate_api_key_for_bot("invalid_key", "bot-1") is None

    def test_list_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        generate_api_key("bot-1", label="Key 1")
        generate_api_key("bot-1", label="Key 2")

        keys = list_api_keys("bot-1")
        assert len(keys) == 2
        # Should not contain hash
        assert all("key_hash" not in k for k in keys)

    def test_revoke_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        raw_key, key_id = generate_api_key("bot-1")

        assert revoke_api_key("bot-1", key_id)
        assert validate_api_key_for_bot(raw_key, "bot-1") is None
        assert len(list_api_keys("bot-1")) == 0

    def test_revoke_nonexistent_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        assert not revoke_api_key("bot-1", "nonexistent")

    def test_origin_check_empty_list_blocks_cross_origin(self):
        """P1-4: Empty allowed_origins blocks cross-origin (fail-closed)."""
        record = APIKeyRecord(
            key_id="k1", key_hash="h1", bot_id="b1", allowed_origins=[],
        )
        # Non-browser (no origin) is allowed
        assert check_origin(record, None)
        # Cross-origin is blocked
        assert not check_origin(record, "https://example.com")

    def test_origin_check_wildcard_allows_all(self):
        """P1-4: Explicit wildcard allows all origins."""
        record = APIKeyRecord(
            key_id="k1", key_hash="h1", bot_id="b1", allowed_origins=["*"],
        )
        assert check_origin(record, "https://anything.com")
        assert check_origin(record, None)

    def test_origin_check_with_restriction(self):
        record = APIKeyRecord(
            key_id="k1", key_hash="h1", bot_id="b1",
            allowed_origins=["https://allowed.com"],
        )
        assert check_origin(record, "https://allowed.com")
        assert not check_origin(record, "https://other.com")
        # Non-browser request (no origin) is allowed
        assert check_origin(record, None)

    def test_key_scoped_to_bot(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        raw_key, _ = generate_api_key("bot-1")

        # Should not validate for a different bot
        assert validate_api_key_for_bot(raw_key, "bot-2") is None
        # Should validate for the correct bot
        assert validate_api_key_for_bot(raw_key, "bot-1") is not None
