"""Security-specific tests for LOKO Bot.

Covers: path traversal (P0-4), SSRF prevention (P1-3), bot_id validation.
"""

from __future__ import annotations

import pytest

from loko.bot.models import validate_slug
from loko.bot.session_store import get_bot_dir


class TestSlugValidation:
    def test_valid_slugs(self):
        assert validate_slug("my-bot") == "my-bot"
        assert validate_slug("bot123") == "bot123"
        assert validate_slug("a") == "a"
        assert validate_slug("bot_test-1") == "bot_test-1"

    def test_invalid_slugs(self):
        with pytest.raises(ValueError):
            validate_slug("..")
        with pytest.raises(ValueError):
            validate_slug("../../etc")
        with pytest.raises(ValueError):
            validate_slug("")
        with pytest.raises(ValueError):
            validate_slug("-leading-dash")
        with pytest.raises(ValueError):
            validate_slug("_leading-underscore")
        with pytest.raises(ValueError):
            validate_slug("HAS_UPPERCASE")
        with pytest.raises(ValueError):
            validate_slug("has space")
        with pytest.raises(ValueError):
            validate_slug("a" * 65)  # Too long


class TestPathTraversalGuard:
    def test_get_bot_dir_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            get_bot_dir("..")
        with pytest.raises(ValueError):
            get_bot_dir("../../etc")

    def test_get_bot_dir_no_create(self, tmp_path, monkeypatch):
        """P0-4: Read-only lookup does not create directories."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        bot_dir = get_bot_dir("nonexistent-bot", create=False)
        assert not bot_dir.exists()

    def test_get_bot_dir_valid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        bot_dir = get_bot_dir("my-test-bot")
        assert bot_dir.exists()
        assert "my-test-bot" in str(bot_dir)


class TestCrawlerSSRF:
    def test_private_ip_blocked(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("http://127.0.0.1/something")

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("http://169.254.169.254/")

    def test_non_http_scheme_blocked(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("ftp://example.com/file")

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("file:///etc/passwd")

    def test_public_url_allowed(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        # Should not raise for public URLs
        _validate_url_ssrf("https://example.com/page")

    def test_private_allowed_when_configured(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        # Should not raise when explicitly allowing private
        _validate_url_ssrf("http://127.0.0.1/page", allow_private=True)
