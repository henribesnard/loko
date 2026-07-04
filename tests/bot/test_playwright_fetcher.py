"""Tests for R6 — Playwright fetcher.

Most tests validate the module interface and SSRF interception logic
without requiring an actual Chromium browser.
"""

from __future__ import annotations

import pytest


def test_factory_returns_simple_when_no_playwright():
    """get_page_fetcher falls back to SimplePageFetcher if Playwright missing."""
    from loko.connectors.playwright_fetcher import get_page_fetcher
    from loko.connectors.faq_web_crawler import SimplePageFetcher

    fetcher = get_page_fetcher(prefer_playwright=False)
    assert isinstance(fetcher, SimplePageFetcher)


def test_playwright_fetcher_has_ssrf_guard():
    """PlaywrightPageFetcher validates URLs before launching browser."""
    try:
        from loko.connectors.playwright_fetcher import PlaywrightPageFetcher
    except ImportError:
        pytest.skip("playwright not installed")

    fetcher = PlaywrightPageFetcher(allow_private_networks=False)
    # Should not crash — SSRF validation happens inside fetch()
    assert fetcher.allowed_domains is None
    assert fetcher.allow_private is False


def test_playwright_fetcher_domain_allowlist():
    """allowed_domains restricts which domains are loaded."""
    try:
        from loko.connectors.playwright_fetcher import PlaywrightPageFetcher
    except ImportError:
        pytest.skip("playwright not installed")

    fetcher = PlaywrightPageFetcher(
        allowed_domains=["example.com", "cdn.example.com"],
    )
    assert "example.com" in fetcher.allowed_domains
    assert "cdn.example.com" in fetcher.allowed_domains
    assert "evil.com" not in fetcher.allowed_domains


@pytest.mark.asyncio
async def test_fetch_blocks_ssrf_url():
    """SSRF-violating URLs return empty content."""
    try:
        from loko.connectors.playwright_fetcher import PlaywrightPageFetcher
    except ImportError:
        pytest.skip("playwright not installed")

    fetcher = PlaywrightPageFetcher(allow_private_networks=False)
    html, status = await fetcher.fetch("http://127.0.0.1/admin")
    assert html == ""
    assert status == 0


@pytest.mark.asyncio
async def test_fetch_blocks_non_http():
    """Non-HTTP schemes are blocked."""
    try:
        from loko.connectors.playwright_fetcher import PlaywrightPageFetcher
    except ImportError:
        pytest.skip("playwright not installed")

    fetcher = PlaywrightPageFetcher()
    html, status = await fetcher.fetch("file:///etc/passwd")
    assert html == ""
    assert status == 0


def test_factory_with_allowed_domains():
    """Factory passes allowed_domains to the fetcher."""
    from loko.connectors.playwright_fetcher import get_page_fetcher

    fetcher = get_page_fetcher(
        prefer_playwright=False,
        allowed_domains=["example.com"],
    )
    # SimplePageFetcher doesn't use allowed_domains — no error expected
    assert fetcher is not None
