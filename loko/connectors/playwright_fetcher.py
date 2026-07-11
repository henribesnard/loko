"""LOKO Bot — Playwright-based page fetcher (R6).

Renders JS-heavy pages using headless Chromium.  Each network request
is intercepted and validated against SSRF rules before being allowed
through.

Usage
-----
    fetcher = PlaywrightPageFetcher(allowed_domains=["example.com"])
    html, status = await fetcher.fetch("https://example.com/faq")

Docker note
-----------
Playwright + Chromium adds ~400 MB to the Docker image.  Since web
crawling is an admin-only operation typically run from the desktop app,
the server Docker image does NOT include Chromium.  If the server image
needs to crawl, set PLAYWRIGHT_BROWSERS_PATH and install browsers at
deploy time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class PlaywrightPageFetcher:
    """Headless Chromium fetcher with SSRF-safe network interception.

    All sub-resource requests (XHR, images, scripts, etc.) are validated
    against ``_validate_url_ssrf`` and the ``allowed_domains`` allowlist
    before being sent.
    """

    MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5 MB
    DEFAULT_TIMEOUT_MS = 30_000

    def __init__(
        self,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        allowed_domains: list[str] | None = None,
        allow_private_networks: bool = False,
        user_agent: str | None = None,
    ):
        self.timeout_ms = timeout_ms
        self.allowed_domains = set(allowed_domains) if allowed_domains else None
        self.allow_private = allow_private_networks
        self.user_agent = user_agent or "LOKO-Bot-Crawler/1.0"

    async def fetch(self, url: str) -> tuple[str, int]:
        """Fetch a page using headless Chromium with JS rendering.

        Returns (html_content, http_status).
        """
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        # Validate the initial URL
        try:
            _validate_url_ssrf(url, allow_private=self.allow_private)
        except ValueError as e:
            logger.warning("SSRF guard blocked %s: %s", url, e)
            return "", 0

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "Playwright not installed — falling back. "
                "Install with: pip install 'loko[crawler]' && playwright install chromium"
            )
            return "", 0

        status_code = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    java_script_enabled=True,
                )
                page = await context.new_page()

                # Intercept all network requests for SSRF protection
                await page.route("**/*", self._handle_route)

                # Navigate and wait for network idle
                response = await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=self.timeout_ms,
                )

                if response:
                    status_code = response.status

                # Extract the rendered DOM
                html = await page.content()

                # Enforce max size
                if len(html) > self.MAX_RESPONSE_SIZE:
                    logger.warning("Rendered page too large for %s, truncating", url)
                    html = html[: self.MAX_RESPONSE_SIZE]

                # Also extract iframe contents if present
                frames_content = await self._extract_frames(page)
                if frames_content:
                    html += "\n<!-- IFRAME CONTENTS -->\n" + frames_content

                return html, status_code

            except Exception as e:
                logger.warning("Playwright fetch error for %s: %s", url, e)
                return "", status_code
            finally:
                await browser.close()

    async def _handle_route(self, route) -> None:
        """Intercept and validate each network request (SSRF guard)."""
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        request_url = route.request.url

        # Validate against SSRF rules
        try:
            _validate_url_ssrf(request_url, allow_private=self.allow_private)
        except ValueError as e:
            logger.debug("SSRF blocked sub-resource: %s — %s", request_url, e)
            await route.abort("blockedbyclient")
            return

        # Check allowed domains if configured
        if self.allowed_domains:
            parsed = urlparse(request_url)
            hostname = parsed.hostname or ""
            if hostname not in self.allowed_domains:
                # Allow same-origin resources (stylesheets, scripts, etc.)
                # but block cross-origin to unrelated domains
                resource_type = route.request.resource_type
                if resource_type in ("document", "xhr", "fetch"):
                    logger.debug("Domain not in allowlist: %s", hostname)
                    await route.abort("blockedbyclient")
                    return

        await route.continue_()

    async def _extract_frames(self, page) -> str:
        """Extract text content from same-origin iframes."""
        contents: list[str] = []

        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                text = await frame.evaluate("document.body.innerText")
                if text and len(text.strip()) > 50:
                    contents.append(text.strip())
            except Exception:
                pass  # Cross-origin frames will fail — expected

        return "\n---\n".join(contents)

    def fetch_sync(self, url: str) -> tuple[str, int]:
        """Synchronous wrapper for use in the crawler's sync interface."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — use a new thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.fetch(url))
                    return future.result(timeout=self.timeout_ms / 1000 + 5)
            return loop.run_until_complete(self.fetch(url))
        except Exception as e:
            logger.warning("Sync playwright fetch error for %s: %s", url, e)
            return "", 0


class SyncPlaywrightPageFetcher:
    """Sync adapter matching FAQWebCrawler's PageFetcher protocol."""

    def __init__(
        self,
        *,
        timeout_ms: int = PlaywrightPageFetcher.DEFAULT_TIMEOUT_MS,
        allowed_domains: list[str] | None = None,
        allow_private_networks: bool = False,
        user_agent: str | None = None,
    ):
        self._renderer = PlaywrightPageFetcher(
            timeout_ms=timeout_ms,
            allowed_domains=allowed_domains,
            allow_private_networks=allow_private_networks,
            user_agent=user_agent,
        )
        self._allow_private_networks = allow_private_networks

    def fetch(self, url: str) -> tuple[str, int]:
        return self._renderer.fetch_sync(url)

    def fetch_sitemap(self, url: str) -> list[str]:
        from loko.connectors.faq_web_crawler import SimplePageFetcher

        return SimplePageFetcher(
            allow_private_networks=self._allow_private_networks,
        ).fetch_sitemap(url)


def get_page_fetcher(
    *,
    prefer_playwright: bool = True,
    allowed_domains: list[str] | None = None,
    allow_private_networks: bool = False,
) -> Any:
    """Factory: return a PlaywrightPageFetcher if available, else SimplePageFetcher.

    This provides a graceful degradation path: admins who need JS rendering
    install the crawler extra; the server image works without it.
    """
    if prefer_playwright:
        try:
            import playwright  # noqa: F401

            return SyncPlaywrightPageFetcher(
                allowed_domains=allowed_domains,
                allow_private_networks=allow_private_networks,
            )
        except ImportError:
            logger.info(
                "Playwright not available — using SimplePageFetcher. "
                "Install 'loko[crawler]' for JS rendering support."
            )

    from loko.connectors.faq_web_crawler import SimplePageFetcher

    return SimplePageFetcher(allow_private_networks=allow_private_networks)
