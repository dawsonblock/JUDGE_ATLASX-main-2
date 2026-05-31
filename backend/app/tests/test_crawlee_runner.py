"""Tests for Crawlee web monitor runner.

These tests verify the runner's safety controls and integration points.
"""

import pytest

from app.db.session import SessionLocal
from app.ingestion.web_monitor import (
    CrawleeRunner,
    WebMonitorTarget,
    run_web_monitor_target_sync,
)
from app.models.entities import SourceSnapshot


class TestCrawleeRunnerSafety:
    """Test runner safety controls."""

    def test_runner_enforces_allowlist(self):
        """Runner should reject URLs not in allowlist."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            runner = CrawleeRunner(target, db)

            # Should allow URLs in allowlist
            assert runner._is_url_allowed("https://example.com/news/article")
            assert runner._is_url_allowed("https://sub.example.com/page")

            # Should reject URLs not in allowlist
            assert not runner._is_url_allowed("https://malicious.com/")
            assert not runner._is_url_allowed("https://other-site.com/")
            assert not runner._is_url_allowed("https://example.com.malicious.com/")

    def test_runner_enforces_max_requests(self):
        """Runner should stop when max_requests is reached."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            max_requests=5,
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            runner = CrawleeRunner(target, db)

            # Initially under limit
            assert runner._check_request_limit()

            # Simulate reaching limit
            runner.request_count = 5
            assert not runner._check_request_limit()

            # Beyond limit
            runner.request_count = 10
            assert not runner._check_request_limit()

    def test_runner_creates_snapshots_with_required_fields(self):
        """Snapshot should include all required provenance fields."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            runner = CrawleeRunner(target, db)

            content = b"Test HTML content"
            snapshot = runner._create_snapshot(
                source_url="https://example.com/news/article-1",
                http_status=200,
                content_type="text/html",
                content=content,
                title="Test Article",
                text_excerpt="Test excerpt content...",
            )

            # Verify all required fields
            assert snapshot.source_url == "https://example.com/news/article-1"
            assert snapshot.http_status == 200
            assert snapshot.content_type == "text/html"
            assert snapshot.content_hash is not None
            assert len(snapshot.content_hash) == 64  # SHA256 hex
            assert snapshot.extracted_text == "Test excerpt content..."
            # Target name is stored as extractor_name, not prepended to raw content
            assert snapshot.extractor_name == "Test Target"
            assert snapshot.raw_content == "Test HTML content"
            assert snapshot.fetched_at is not None

    def test_runner_snapshot_hash_is_deterministic(self):
        """Same content should produce same hash."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            runner = CrawleeRunner(target, db)

            content = b"Same content"
            snapshot1 = runner._create_snapshot(
                source_url="https://example.com/1",
                http_status=200,
                content_type="text/html",
                content=content,
            )
            snapshot2 = runner._create_snapshot(
                source_url="https://example.com/2",
                http_status=200,
                content_type="text/html",
                content=content,
            )

            # Same content = same hash
            assert snapshot1.content_hash == snapshot2.content_hash

    def test_runner_snapshot_handles_string_content(self):
        """Snapshot should handle both string and bytes content."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            runner = CrawleeRunner(target, db)

            # String content
            snapshot_str = runner._create_snapshot(
                source_url="https://example.com/1",
                http_status=200,
                content_type="text/html",
                content="String content",
            )

            # Bytes content with same text
            snapshot_bytes = runner._create_snapshot(
                source_url="https://example.com/2",
                http_status=200,
                content_type="text/html",
                content=b"String content",
            )

            # Should produce same hash
            assert snapshot_str.content_hash == snapshot_bytes.content_hash


class TestCrawleeRunnerIntegration:
    """Test runner integration with source registry."""

    def test_runner_checks_source_registry(self):
        """Runner should check source registry before running."""
        target = WebMonitorTarget(
            source_key="test_registry_check",
            name="Test Registry Check",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            enabled=False,  # Disabled in registry
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            # This should create a disabled registry entry
            run = run_web_monitor_target_sync(target, db)

            # Should fail because target is disabled
            assert run.status == "failed"
            assert run.error_count >= 1
            assert any("disabled" in str(e).lower() for e in run.errors)

    def test_runner_respects_disabled_target(self):
        """Disabled target should not create public records."""
        target = WebMonitorTarget(
            source_key="disabled_target_test",
            name="Disabled Target Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            enabled=False,
            extractor_type="rss_or_news_listing",
        )

        with SessionLocal() as db:
            run = run_web_monitor_target_sync(target, db)

            # Should fail closed
            assert run.status in ["failed", "completed_with_warnings"]

            # Should not create any snapshots with this target's metadata
            snapshots = db.query(SourceSnapshot).filter(
                SourceSnapshot.raw_content.contains("Disabled Target Test")
            ).all()
            assert len(snapshots) == 0


class TestCrawleeRunnerLimits:
    """Test runner enforces safety limits."""

    def test_target_has_sensible_defaults(self):
        """Target should have safe defaults."""
        target = WebMonitorTarget(
            source_key="defaults_test",
            name="Defaults Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        # Safe defaults
        assert target.enabled is False
        assert target.max_depth == 1
        assert target.max_requests == 25
        assert target.concurrency == 2
        assert target.source_tier == "news_only_context"
        assert target.robots_txt_obey is True

    def test_target_enforces_max_depth_limit(self):
        """Target should enforce max_depth <= 3."""
        with pytest.raises(ValueError):
            WebMonitorTarget(
                source_key="too_deep",
                name="Too Deep",
                source_type="news_only_context",
                base_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com/news/"],
                max_depth=5,  # Too deep
                extractor_type="rss_or_news_listing",
            )

    def test_target_enforces_max_requests_limit(self):
        """Target should enforce max_requests <= 100."""
        with pytest.raises(ValueError):
            WebMonitorTarget(
                source_key="too_many_requests",
                name="Too Many Requests",
                source_type="news_only_context",
                base_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com/news/"],
                max_requests=500,  # Too many
                extractor_type="rss_or_news_listing",
            )

    def test_target_enforces_concurrency_limit(self):
        """Target should enforce concurrency <= 5."""
        with pytest.raises(ValueError):
            WebMonitorTarget(
                source_key="too_concurrent",
                name="Too Concurrent",
                source_type="news_only_context",
                base_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com/news/"],
                concurrency=10,  # Too high
                extractor_type="rss_or_news_listing",
            )

    def test_target_requires_non_empty_allowlist(self):
        """Target should require at least one allowed domain."""
        with pytest.raises(ValueError):
            WebMonitorTarget(
                source_key="no_allowlist",
                name="No Allowlist",
                source_type="news_only_context",
                base_url="https://example.com",
                allowed_domains=[],  # Empty!
                start_urls=["https://example.com/news/"],
                extractor_type="rss_or_news_listing",
            )
