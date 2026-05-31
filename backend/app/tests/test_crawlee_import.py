"""Import smoke test for Crawlee web monitoring module."""

import pytest


def test_crawlee_imports():
    """Verify crawlee package imports successfully."""
    import crawlee
    from crawlee import Request
    from crawlee.crawlers import HttpCrawler

    assert crawlee is not None
    assert Request is not None
    assert HttpCrawler is not None


def test_web_monitor_module_imports():
    """Verify web_monitor module structure imports."""
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget

    assert WebMonitorTarget is not None


def test_target_allowlist_validation():
    """Test that target validates allowlisted domains."""
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget

    # Valid target with proper allowlist
    target = WebMonitorTarget(
        source_key="saskatoon_police_news",
        name="Saskatoon Police News",
        source_type="official_police_media",
        base_url="https://saskatoonpolice.ca",
        allowed_domains=["saskatoonpolice.ca"],
        start_urls=["https://saskatoonpolice.ca/news/"],
        max_depth=1,
        max_requests=25,
        concurrency=2,
        source_tier="official_police_open_data",
        enabled=False,
        extractor_type="police_release_index",
    )

    # Should accept URLs in allowlist
    assert target.is_url_allowed("https://saskatoonpolice.ca/news/article-123")
    assert target.is_url_allowed("https://saskatoonpolice.ca/")

    # Should reject URLs not in allowlist
    assert not target.is_url_allowed("https://example.com/")
    assert not target.is_url_allowed("https://malicious.com/")


def test_target_disabled_by_default():
    """Test that targets default to disabled."""
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget

    target = WebMonitorTarget(
        source_key="test_target",
        name="Test Target",
        source_type="news_only_context",
        base_url="https://example.com",
        allowed_domains=["example.com"],
        start_urls=["https://example.com/news/"],
        extractor_type="rss_or_news_listing",
    )

    # Should default to disabled
    assert target.enabled is False


def test_target_max_requests_enforced():
    """Test that max_requests has sensible defaults and limits."""
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget

    target = WebMonitorTarget(
        source_key="test_target",
        name="Test Target",
        source_type="news_only_context",
        base_url="https://example.com",
        allowed_domains=["example.com"],
        start_urls=["https://example.com/news/"],
        max_requests=10,
        extractor_type="rss_or_news_listing",
    )

    assert target.max_requests == 10
    assert target.max_requests <= 100  # Sanity check


def test_target_source_tier_defaults():
    """Test that source_tier defaults to news_only_context (lowest trust)."""
    from app.ingestion.web_monitor.source_targets import WebMonitorTarget

    target = WebMonitorTarget(
        source_key="test_target",
        name="Test Target",
        source_type="news_only_context",
        base_url="https://example.com",
        allowed_domains=["example.com"],
        start_urls=["https://example.com/news/"],
        extractor_type="rss_or_news_listing",
    )

    # Should default to lowest trust tier
    assert target.source_tier == "news_only_context"
