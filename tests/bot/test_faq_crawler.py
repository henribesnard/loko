"""Tests for the FAQ web crawler connector."""

import pytest

from loko.connectors.faq_web_crawler import (
    CrawlConfig,
    CrawledDocument,
    FAQWebCrawler,
    SimplePageFetcher,
    content_hash,
    extract_content,
)


# ---------------------------------------------------------------------------
# Mock fetcher
# ---------------------------------------------------------------------------

class MockPageFetcher:
    """In-memory page fetcher for testing."""

    def __init__(self, pages: dict[str, str] | None = None):
        self.pages: dict[str, str] = pages or {}
        self.fetched: list[str] = []

    def add_page(self, url: str, html: str) -> None:
        self.pages[url] = html

    def fetch(self, url: str) -> tuple[str, int]:
        self.fetched.append(url)
        if url in self.pages:
            return self.pages[url], 200
        return "", 404

    def fetch_sitemap(self, url: str) -> list[str]:
        html, status = self.fetch(url)
        if status != 200:
            return []
        import re
        return [m.group(1) for m in re.finditer(r"<loc>(.*?)</loc>", html)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAQ_HTML = """
<!DOCTYPE html>
<html>
<head><title>FAQ - Mon Aide</title></head>
<body>
<nav><a href="/">Accueil</a></nav>
<main>
<article>
<h1>Comment réinitialiser mon mot de passe ?</h1>
<p>Pour réinitialiser votre mot de passe, rendez-vous dans les paramètres de votre compte
et cliquez sur "Mot de passe oublié". Un email de vérification vous sera envoyé.</p>
</article>
</main>
<footer>Copyright 2024</footer>
<script>console.log("tracking")</script>
</body>
</html>
"""

FAQ_HTML_2 = """
<!DOCTYPE html>
<html>
<head><title>FAQ - Facturation</title></head>
<body>
<main>
<article>
<h1>Comment modifier mon abonnement ?</h1>
<p>Pour modifier votre abonnement, accédez à la page de gestion de compte.
Vous pouvez changer de formule à tout moment. Le changement prend effet immédiatement.</p>
<a href="https://example.com/faq/password">Réinitialisation mot de passe</a>
<a href="https://example.com/faq/contact">Contacter le support</a>
</article>
</main>
</body>
</html>
"""

SHORT_HTML = """
<html><body><p>OK</p></body></html>
"""

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/faq/password</loc></url>
  <url><loc>https://example.com/faq/billing</loc></url>
  <url><loc>https://example.com/faq/contact</loc></url>
</urlset>
"""

IFRAME_HTML = """
<html>
<body>
<h1>Help Center</h1>
<iframe src="https://example.com/faq/password"></iframe>
<a href="https://example.com/faq/billing">Facturation</a>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Tests: extract_content
# ---------------------------------------------------------------------------

class TestExtractContent:
    def test_extracts_title(self):
        title, _ = extract_content(FAQ_HTML)
        assert "FAQ - Mon Aide" in title

    def test_extracts_body_text(self):
        _, text = extract_content(FAQ_HTML)
        assert "réinitialiser votre mot de passe" in text

    def test_removes_nav_footer_script(self):
        _, text = extract_content(FAQ_HTML)
        assert "Accueil" not in text
        assert "Copyright" not in text
        assert "tracking" not in text

    def test_extracts_main_article(self):
        _, text = extract_content(FAQ_HTML)
        assert "mot de passe" in text

    def test_handles_empty_html(self):
        title, text = extract_content("")
        assert title == ""
        assert text == ""

    def test_decodes_html_entities(self):
        html = "<html><body>&amp; &lt;hello&gt; &quot;world&quot;</body></html>"
        _, text = extract_content(html)
        assert '& <hello> "world"' in text


# ---------------------------------------------------------------------------
# Tests: content_hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_deterministic(self):
        h1 = content_hash("hello world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_different_for_different_content(self):
        h1 = content_hash("hello")
        h2 = content_hash("world")
        assert h1 != h2

    def test_returns_16_chars(self):
        h = content_hash("test")
        assert len(h) == 16


# ---------------------------------------------------------------------------
# Tests: FAQWebCrawler
# ---------------------------------------------------------------------------

class TestFAQWebCrawler:
    def test_crawl_single_page(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq": FAQ_HTML,
        })
        config = CrawlConfig(start_url="https://example.com/faq")
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        assert len(result.documents) == 1
        assert "mot de passe" in result.documents[0].content
        assert result.urls_visited >= 1

    def test_crawl_follows_links(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq/billing": FAQ_HTML_2,
            "https://example.com/faq/password": FAQ_HTML,
        })
        config = CrawlConfig(start_url="https://example.com/faq/billing", max_depth=2)
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        assert len(result.documents) >= 1
        urls = {d.url for d in result.documents}
        assert "https://example.com/faq/billing" in urls

    def test_crawl_respects_max_pages(self):
        fetcher = MockPageFetcher({
            f"https://example.com/page{i}": f"<html><body><p>Content for page {i} with enough text to pass filter.</p><a href='https://example.com/page{i+1}'>Next</a></body></html>"
            for i in range(20)
        })
        config = CrawlConfig(start_url="https://example.com/page0", max_pages=5, max_depth=5)
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        assert result.urls_visited <= 5

    def test_crawl_skips_short_content(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq": SHORT_HTML,
        })
        config = CrawlConfig(start_url="https://example.com/faq", min_content_length=50)
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        assert len(result.documents) == 0

    def test_crawl_skips_other_domains(self):
        html = '<html><body><p>Some content here for testing.</p><a href="https://other.com/page">External</a></body></html>'
        fetcher = MockPageFetcher({
            "https://example.com/faq": html,
        })
        config = CrawlConfig(start_url="https://example.com/faq")
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        for url in fetcher.fetched:
            assert "other.com" not in url

    def test_crawl_with_sitemap(self):
        fetcher = MockPageFetcher({
            "https://example.com/sitemap.xml": SITEMAP_XML,
            "https://example.com/faq/password": FAQ_HTML,
            "https://example.com/faq/billing": FAQ_HTML_2,
        })
        config = CrawlConfig(start_url="https://example.com/faq")
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        assert len(result.documents) >= 2

    def test_crawl_incremental_skips_unchanged(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq": FAQ_HTML,
        })
        config = CrawlConfig(start_url="https://example.com/faq")
        crawler = FAQWebCrawler(config, fetcher=fetcher)

        # First crawl
        result1 = crawler.crawl()
        assert len(result1.documents) == 1

        # Second crawl with known hashes
        known_hashes = {d.url: d.content_hash for d in result1.documents}
        result2 = crawler.crawl(known_hashes=known_hashes)
        assert len(result2.documents) == 0
        assert result2.urls_skipped >= 1

    def test_crawl_exclude_patterns(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq": FAQ_HTML_2,
            "https://example.com/faq/contact": FAQ_HTML,
        })
        config = CrawlConfig(
            start_url="https://example.com/faq",
            exclude_patterns=[r"/contact"],
            max_depth=2,
        )
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        urls = {d.url for d in result.documents}
        assert "https://example.com/faq/contact" not in urls

    def test_crawl_follows_iframes(self):
        fetcher = MockPageFetcher({
            "https://example.com/help": IFRAME_HTML,
            "https://example.com/faq/password": FAQ_HTML,
            "https://example.com/faq/billing": FAQ_HTML_2,
        })
        config = CrawlConfig(
            start_url="https://example.com/help",
            follow_iframes=True,
            max_depth=2,
        )
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        urls = {d.url for d in result.documents}
        assert "https://example.com/faq/password" in urls

    def test_crawl_metadata_includes_intents(self):
        fetcher = MockPageFetcher({
            "https://example.com/faq": FAQ_HTML,
        })
        config = CrawlConfig(
            start_url="https://example.com/faq",
            bot_intents=["facturation"],
            confidentiality="interne",
        )
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        doc = result.documents[0]
        assert doc.metadata["bot_intents"] == ["facturation"]
        assert doc.metadata["confidentiality"] == "interne"

    def test_crawl_skips_binary_files(self):
        html = '<html><body><p>Content for testing.</p><a href="https://example.com/file.pdf">PDF</a><a href="https://example.com/img.jpg">Image</a></body></html>'
        fetcher = MockPageFetcher({
            "https://example.com/page": html,
        })
        config = CrawlConfig(start_url="https://example.com/page", max_depth=2)
        crawler = FAQWebCrawler(config, fetcher=fetcher)
        result = crawler.crawl()

        for url in fetcher.fetched:
            assert not url.endswith(".pdf")
            assert not url.endswith(".jpg")


# ---------------------------------------------------------------------------
# Tests: R3 — SSRF redirect revalidation
# ---------------------------------------------------------------------------

class TestSSRFRedirect:
    """R3: Redirect targets must be re-validated against SSRF rules."""

    def test_validate_url_ssrf_rejects_private_ip(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("http://127.0.0.1/secret")

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("http://169.254.169.254/latest/meta-data")

    def test_validate_url_ssrf_rejects_non_http(self):
        from loko.connectors.faq_web_crawler import _validate_url_ssrf

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("file:///etc/passwd")

        with pytest.raises(ValueError, match="SSRF"):
            _validate_url_ssrf("ftp://internal/data")

    def test_resolve_and_pin_rejects_loopback(self):
        """DNS pinning must reject IPs that resolve to private addresses."""
        fetcher = SimplePageFetcher(allow_private_networks=False)

        with pytest.raises(ValueError, match="SSRF"):
            fetcher._resolve_and_pin("http://127.0.0.1/test")

    def test_max_redirects_enforced(self):
        """Fetcher must stop after MAX_REDIRECTS hops."""
        fetcher = SimplePageFetcher(allow_private_networks=True)
        assert fetcher.MAX_REDIRECTS == 5
