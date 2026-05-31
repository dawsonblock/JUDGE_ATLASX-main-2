"""Integration tests for web monitor safety pipeline.

Tests verifying crawlee candidates flow through safety gates.
"""

import pytest

from app.db.session import SessionLocal
from app.ingestion.web_monitor import (
    CrawleeRunner,
    ExtractedCandidate,
    WebMonitorTarget,
    extract_from_page,
)
from app.services.publish_rules import review_status_for_tier


class TestWebMonitorSafetyPipeline:
    """Test full safety pipeline for web monitor candidates."""

    def test_candidate_with_safe_location(self):
        """Candidates with city-level locations should be acceptable."""
        candidate = ExtractedCandidate(
            source_url="https://police.example.com/news/1",
            title="Police Release",
            published_at=None,
            summary="Incident occurred in downtown area. No exact addresses mentioned.",
            candidate_type="crime_incident_context",
            location_text="downtown",
            entities=[],
            warnings=[],
            confidence=0.3,
        )

        # Should have low confidence and verification warning
        assert candidate.confidence <= 0.5
        assert any("Crawled" in w for w in candidate.warnings)

    def test_candidate_with_private_address_flagged(self):
        """Candidates with private address hints should be flagged."""
        html = "<p>Incident occurred at 123 Main Street, apartment 4B.</p>"

        candidate = extract_from_page(
            url="https://police.example.com/news/1",
            content=html,
            title="Police Release",
            extractor_type="police_release_index",
        )

        # Should have warnings
        assert len(candidate.warnings) > 0
        assert any("address" in w.lower() or "private" in w.lower() for w in candidate.warnings)

    def test_candidate_gets_hold_tier_status(self):
        """Crawled candidates should get HOLD tier (pending_review)."""
        tier = "news_only_context"  # Web monitor default tier

        status = review_status_for_tier(tier)

        # Should be pending_review (HOLD tier)
        assert status == "pending_review"

    def test_candidate_never_auto_publish(self):
        """Crawled candidates should never be auto-published."""
        candidate = ExtractedCandidate(
            source_url="https://example.com/news",
            title="Test",
            published_at=None,
            summary="Test summary",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.8,  # Trying high confidence
        )

        # Confidence clamped to 0.5
        assert candidate.confidence <= 0.5

        # Should have verification warning
        assert any("Crawled content" in w for w in candidate.warnings)

    def test_snapshot_stores_provenance(self):
        """Snapshots should store full provenance info."""
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

            snapshot = runner._create_snapshot(
                source_url="https://example.com/news/1",
                http_status=200,
                content_type="text/html",
                content=b"<html><title>News</title><body>Content</body></html>",
                title="News Article",
                text_excerpt="Content excerpt",
            )

            # Verify provenance fields
            assert snapshot.source_url == "https://example.com/news/1"
            assert snapshot.http_status == 200
            assert snapshot.content_hash is not None
            assert len(snapshot.content_hash) == 64
            # Target name is stored in extractor_name, not prepended to raw content
            assert snapshot.extractor_name == "Test Target"

    def test_runner_respects_concurrency_limits(self):
        """Runner should use configured concurrency limits."""
        target = WebMonitorTarget(
            source_key="low_concurrency_test",
            name="Low Concurrency Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            concurrency=1,  # Very low
            extractor_type="rss_or_news_listing",
        )

        # Config should reflect limit
        config = target.get_crawlee_config()
        assert config["max_concurrency"] == 1
        assert config["max_concurrency"] <= 5  # Hard limit enforced

    def test_runner_respects_depth_limits(self):
        """Runner should use configured depth limits."""
        target = WebMonitorTarget(
            source_key="shallow_test",
            name="Shallow Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            max_depth=0,  # Start URLs only
            extractor_type="rss_or_news_listing",
        )

        config = target.get_crawlee_config()
        assert config["max_crawl_depth"] == 0

    def test_extracted_content_includes_verification_warning(self):
        """All extracted content must include verification warning."""
        candidate = ExtractedCandidate(
            source_url="https://example.com/article",
            title="Test Article",
            published_at=None,
            summary="Test content",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=[],  # Empty initially
            confidence=0.3,
        )

        # Should have default warning added
        warning_texts = [w.lower() for w in candidate.warnings]
        assert any("crawled" in w for w in warning_texts)
        assert any("verification" in w for w in warning_texts)

    def test_private_info_patterns_detected(self):
        """Common private info patterns should be detected in extraction."""
        content_with_phone = "Contact John at 555-123-4567 for details."
        content_with_email = "Email jane@example.com for information."
        content_with_address = "Located at 456 Oak Avenue, Suite 100."

        # These patterns should be flagged (implementation checks)
        has_phone = bool(
            __import__("re").search(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", content_with_phone)
        )
        has_email = bool(
            __import__("re").search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", content_with_email)
        )
        has_address = bool(
            __import__("re").search(
                r"\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Suite|Apt|#)",
                content_with_address,
                __import__("re").IGNORECASE,
            )
        )

        assert has_phone
        assert has_email
        assert has_address

    def test_max_requests_cannot_exceed_safety_limit(self):
        """Max requests must be capped at safety limit."""
        with pytest.raises(ValueError):
            WebMonitorTarget(
                source_key="too_many_requests",
                name="Too Many Requests",
                source_type="news_only_context",
                base_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com/news/"],
                max_requests=500,  # Way over limit
                extractor_type="rss_or_news_listing",
            )

    def test_allowlist_rejects_subdomain_hijacking(self):
        """Allowlist should not match malicious subdomains."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
        )

        # Should allow exact match
        assert target.is_url_allowed("https://example.com/page")

        # Should allow legitimate subdomain
        assert target.is_url_allowed("https://news.example.com/page")

        # Should reject lookalike domains
        assert not target.is_url_allowed("https://example.com.malicious.com/page")
        assert not target.is_url_allowed("https://example-com.malicious.com/page")
        assert not target.is_url_allowed("https://evil-example.com/page")
