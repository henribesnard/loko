"""LOKO — FAQ Web Crawler connector.

Crawls FAQ / help-center pages, extracts articles, and produces
Chunk-compatible documents ready for ingestion into the knowledge base.

Features:
  - Sitemap.xml discovery
  - BFS crawl with configurable depth
  - Content extraction and boilerplate removal
  - Incremental re-sync via content hash
  - Per-article metadata: source_url, title, crawl date, hash
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class CrawledDocument(BaseModel):
    """A single crawled FAQ article."""
    doc_id: str
    url: str
    title: str
    content: str
    content_hash: str
    crawled_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawlResult(BaseModel):
    """Result of a crawl operation."""
    documents: list[CrawledDocument] = Field(default_factory=list)
    urls_visited: int = 0
    urls_skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class CrawlConfig(BaseModel):
    """Configuration for the FAQ crawler."""
    start_url: str
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages: int = Field(default=200, ge=1, le=5000)
    allowed_domains: list[str] = Field(default_factory=list)
    url_patterns: list[str] = Field(default_factory=list)  # regex patterns to match
    exclude_patterns: list[str] = Field(default_factory=list)  # regex to exclude
    respect_robots: bool = True
    follow_iframes: bool = True
    min_content_length: int = Field(default=50, ge=10)
    bot_intents: list[str] = Field(default_factory=list)  # intent tags for chunks
    bot_sub_motifs: list[str] = Field(default_factory=list)
    confidentiality: str = "public"


# ---------------------------------------------------------------------------
# Page fetcher protocol (allows mock in tests)
# ---------------------------------------------------------------------------

class PageFetcher(Protocol):
    """Protocol for fetching web pages."""

    def fetch(self, url: str) -> tuple[str, int]:
        """Fetch a URL, return (html_content, status_code)."""
        ...

    def fetch_sitemap(self, url: str) -> list[str]:
        """Parse a sitemap.xml and return discovered URLs."""
        ...


# ---------------------------------------------------------------------------
# Simple fetcher (requests-based, no JS rendering)
# ---------------------------------------------------------------------------

def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/loopback/link-local IP.

    Used to prevent SSRF attacks (P1-3).
    """
    import ipaddress
    import socket

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except socket.gaierror:
        return True  # Cannot resolve → reject (fail-closed)

    for family, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_multicast
            ):
                return True
        except ValueError:
            return True

    return False


def _validate_url_ssrf(url: str, allow_private: bool = False) -> None:
    """Validate a URL against SSRF: reject private IPs and non-http(s) schemes."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"SSRF blocked: unsupported scheme {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("SSRF blocked: no hostname in URL")

    if not allow_private and _is_private_ip(hostname):
        raise ValueError(f"SSRF blocked: private/reserved IP for {hostname}")


class SimplePageFetcher:
    """HTTP fetcher using urllib (no JS rendering).

    For FAQ pages that require JS rendering, swap in a Playwright-based
    fetcher implementing the same PageFetcher protocol.
    """

    MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5 MB

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str | None = None,
        allow_private_networks: bool = False,
    ):
        self.timeout = timeout
        self.user_agent = user_agent or "LOKO-Bot-Crawler/1.0"
        self.allow_private = allow_private_networks
        self._robots_cache: dict[str, Any] = {}

    def fetch(self, url: str) -> tuple[str, int]:
        import urllib.error
        import urllib.request

        # SSRF guard (P1-3)
        try:
            _validate_url_ssrf(url, allow_private=self.allow_private)
        except ValueError as e:
            logger.warning("SSRF guard blocked %s: %s", url, e)
            return "", 0

        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # Enforce max response size
                data = resp.read(self.MAX_RESPONSE_SIZE + 1)
                if len(data) > self.MAX_RESPONSE_SIZE:
                    logger.warning("Response too large for %s (>5MB), truncating", url)
                    data = data[: self.MAX_RESPONSE_SIZE]
                return data.decode("utf-8", errors="replace"), resp.status
        except urllib.error.HTTPError as e:
            return "", e.code
        except Exception as e:
            logger.warning("Fetch error for %s: %s", url, e)
            return "", 0

    def check_robots_txt(self, url: str) -> bool:
        """Check if crawling is allowed by robots.txt (P1-3)."""
        import urllib.robotparser

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        if robots_url not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception:
                # If robots.txt is unreachable, allow crawling
                self._robots_cache[robots_url] = None
                return True
            self._robots_cache[robots_url] = rp

        rp = self._robots_cache[robots_url]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def fetch_sitemap(self, url: str) -> list[str]:
        """Parse a sitemap.xml and extract <loc> URLs."""
        html, status = self.fetch(url)
        if status != 200 or not html:
            return []

        # Use xml.etree for safer parsing (P1-3)
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(html)
            # Handle namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            return [loc.text.strip() for loc in root.iter(f"{ns}loc") if loc.text]
        except Exception:
            # Fallback to regex for malformed sitemaps
            urls: list[str] = []
            for match in re.finditer(r"<loc>\s*(.*?)\s*</loc>", html):
                urls.append(match.group(1))
            return urls


# ---------------------------------------------------------------------------
# Content extractor
# ---------------------------------------------------------------------------

def extract_content(html: str) -> tuple[str, str]:
    """Extract title and main text content from HTML.

    Uses simple heuristics to strip boilerplate (nav, footer, header, script).
    Returns (title, body_text).
    """
    # Extract title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    title = re.sub(r"<[^>]+>", "", title)  # strip nested tags

    # Remove unwanted elements
    cleaned = html
    for tag in ("script", "style", "nav", "footer", "header", "aside", "noscript"):
        cleaned = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Try to find main content areas
    main_match = re.search(
        r"<(?:main|article)[^>]*>(.*?)</(?:main|article)>",
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    if main_match:
        cleaned = main_match.group(1)

    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", cleaned)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Decode HTML entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )

    return title, text


def content_hash(text: str) -> str:
    """SHA-256 hash of the text content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

@dataclass
class _CrawlState:
    """Internal crawl state for BFS traversal."""
    visited: set[str] = field(default_factory=set)
    queue: deque[tuple[str, int]] = field(default_factory=deque)  # (url, depth)
    documents: list[CrawledDocument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0


class FAQWebCrawler:
    """BFS-based FAQ web crawler.

    Usage:
        crawler = FAQWebCrawler(config, fetcher=SimplePageFetcher())
        result = crawler.crawl()
        for doc in result.documents:
            # ingest doc into knowledge base
    """

    def __init__(self, config: CrawlConfig, fetcher: PageFetcher | None = None):
        self.config = config
        self.fetcher = fetcher or SimplePageFetcher()
        self._compiled_patterns = [re.compile(p) for p in config.url_patterns]
        self._compiled_excludes = [re.compile(p) for p in config.exclude_patterns]

        # Auto-derive allowed domain from start_url if not specified
        if not config.allowed_domains:
            parsed = urlparse(config.start_url)
            self.allowed_domains = [parsed.netloc]
        else:
            self.allowed_domains = config.allowed_domains

    def crawl(self, known_hashes: dict[str, str] | None = None) -> CrawlResult:
        """Run BFS crawl. Returns discovered documents.

        Args:
            known_hashes: dict of url -> content_hash from previous crawl.
                          Documents with unchanged hash are skipped (incremental sync).
        """
        known = known_hashes or {}
        state = _CrawlState()

        # Try sitemap first
        parsed = urlparse(self.config.start_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        sitemap_urls = self.fetcher.fetch_sitemap(sitemap_url)

        if sitemap_urls:
            for url in sitemap_urls:
                if self._should_visit(url, state):
                    state.queue.append((url, 0))
        else:
            state.queue.append((self.config.start_url, 0))

        # BFS
        while state.queue and len(state.visited) < self.config.max_pages:
            url, depth = state.queue.popleft()

            if url in state.visited:
                continue
            state.visited.add(url)

            if depth > self.config.max_depth:
                state.skipped += 1
                continue

            # robots.txt check (P1-3)
            if self.config.respect_robots and hasattr(self.fetcher, "check_robots_txt"):
                if not self.fetcher.check_robots_txt(url):
                    logger.debug("Robots.txt disallows %s", url)
                    state.skipped += 1
                    continue

            try:
                html, status = self.fetcher.fetch(url)
                if status != 200 or not html:
                    state.skipped += 1
                    continue

                # Discover links for BFS (before content filter, so hub pages
                # with little content still propagate their links)
                if depth < self.config.max_depth:
                    for link_url in self._extract_links(html, url):
                        if self._should_visit(link_url, state):
                            state.queue.append((link_url, depth + 1))

                title, text = extract_content(html)

                if len(text) < self.config.min_content_length:
                    state.skipped += 1
                    continue

                # Check for content change (incremental)
                h = content_hash(text)
                if url in known and known[url] == h:
                    state.skipped += 1
                    continue

                doc = CrawledDocument(
                    doc_id=content_hash(url),
                    url=url,
                    title=title,
                    content=text,
                    content_hash=h,
                    metadata={
                        "bot_intents": self.config.bot_intents,
                        "bot_sub_motifs": self.config.bot_sub_motifs,
                        "confidentiality": self.config.confidentiality,
                        "source_url": url,
                    },
                )
                state.documents.append(doc)

            except Exception as e:
                state.errors.append(f"{url}: {e}")
                logger.warning("Crawl error for %s: %s", url, e)

        return CrawlResult(
            documents=state.documents,
            urls_visited=len(state.visited),
            urls_skipped=state.skipped,
            errors=state.errors,
        )

    def _should_visit(self, url: str, state: _CrawlState) -> bool:
        """Check if a URL should be visited."""
        if url in state.visited:
            return False

        parsed = urlparse(url)

        # Domain check
        if parsed.netloc not in self.allowed_domains:
            return False

        # Exclude patterns
        for pattern in self._compiled_excludes:
            if pattern.search(url):
                return False

        # Include patterns (if specified, URL must match at least one)
        if self._compiled_patterns:
            if not any(p.search(url) for p in self._compiled_patterns):
                return False

        # Skip non-HTTP
        if parsed.scheme not in ("http", "https"):
            return False

        # Skip anchors, files
        path = parsed.path.lower()
        skip_extensions = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".css", ".js")
        if any(path.endswith(ext) for ext in skip_extensions):
            return False

        return True

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract href links from HTML."""
        links: list[str] = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
            href = match.group(1)
            if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
                continue
            absolute = urljoin(base_url, href)
            # Strip fragment
            absolute = absolute.split("#")[0]
            links.append(absolute)

        # Follow iframes if configured
        if self.config.follow_iframes:
            for match in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
                src = match.group(1)
                absolute = urljoin(base_url, src)
                links.append(absolute)

        return links
