"""Tests for candidate to ReviewItem bridge.

Tests that ExtractedCandidates are properly converted to ReviewItems
with correct safety defaults.
"""

import pytest
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.ingestion.web_monitor.extractors import ExtractedCandidate
from app.ingestion.web_monitor.crawlee_runner import CrawleeRunner
from app.ingestion.web_monitor.source_targets import WebMonitorTarget
from app.models.entities import ReviewItem, SourceSnapshot


class TestCandidateReviewBridge:
    """Test conversion of ExtractedCandidate to ReviewItem."""

    def test_candidate_creates_review_item(self, db):
        """ExtractedCandidate should create ReviewItem."""
        target = WebMonitorTarget(
            source_key="test_target",
            name="Test Target",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/news/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        # Create snapshot
        snapshot = SourceSnapshot(
            source_url="https://example.com/news/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="abc123",
            http_status=200,
        )
        db.add(snapshot)
        db.flush()

        # Create candidate
        candidate = ExtractedCandidate(
            source_url="https://example.com/news/1",
            title="Test News",
            published_at=None,
            summary="Test summary",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.3,
        )

        # Convert to ReviewItem
        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item is not None
        assert review_item.record_type == "news_context"
        assert review_item.source_snapshot_id == snapshot.id

    def test_review_item_status_is_pending(self, db):
        """ReviewItem should always have status='pending'."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.5,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.status == "pending"

    def test_publish_recommendation_is_review_required(self, db):
        """ReviewItem should always have publish_recommendation='review_required'."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.8,  # High confidence from extractor
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.publish_recommendation == "review_required"

    def test_confidence_capped_at_0_5(self, db):
        """ReviewItem confidence should be capped at 0.5."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.9,  # Try to set high confidence
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.confidence <= 0.5
        assert review_item.confidence == 0.5  # Capped

    def test_low_confidence_preserved(self, db):
        """Low confidence values should be preserved."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.3,  # Low confidence
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.confidence == 0.3  # Preserved

    def test_private_address_warning_sets_needs_review(self, db):
        """Address warnings should set privacy_status='needs_review'."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="police_release_index",
            source_tier="official_police_open_data",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Police Release",
            published_at=None,
            candidate_type="crime_incident_context",
            summary="Incident at 123 Main Street",
            location_text="downtown",
            entities=[],
            warnings=["Possible private address detected"],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.privacy_status == "needs_review"

    def test_person_name_warning_sets_needs_review(self, db):
        """Person name warnings should set privacy_status='needs_review'."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="police_release_index",
            source_tier="official_police_open_data",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Police Release",
            published_at=None,
            candidate_type="crime_incident_context",
            summary="Officer John Smith responded",
            location_text="downtown",
            entities=[],
            warnings=["Possible person_name detected"],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.privacy_status == "needs_review"

    def test_no_warnings_sets_safe(self, db):
        """No warnings should set privacy_status='safe'."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="News Article",
            published_at=None,
            candidate_type="news_context",
            summary="General news without private info",
            location_text="city center",
            entities=[],
            warnings=[],  # No warnings
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.privacy_status == "safe"

    def test_source_snapshot_id_populated(self, db):
        """ReviewItem should have source_snapshot_id from snapshot."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        assert snapshot.id is not None

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.source_snapshot_id == snapshot.id

    def test_suggested_payload_contains_candidate_data(self, db):
        """ReviewItem payload should contain extracted candidate data."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/1",
            title="Test Title",
            published_at=datetime.now(timezone.utc),
            summary="Test Summary",
            candidate_type="news_context",
            location_text="Test Location",
            entities=[{"type": "person", "name": "Officer"}],
            warnings=["Warning"],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        payload = review_item.suggested_payload_json
        assert payload["title"] == "Test Title"
        assert payload["summary"] == "Test Summary"
        assert payload["candidate_type"] == "news_context"
        assert payload["location_text"] == "Test Location"
        # Warnings include test warning plus auto-added "Crawled content" warning
        assert "Warning" in payload["extracted_warnings"]
        assert "Crawled content - requires verification" in payload["extracted_warnings"]
        assert payload["extraction_confidence"] == 0.3

    def test_source_quality_from_target(self, db):
        """ReviewItem source_quality should come from target source_tier."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="official_police_open_data",
            base_url="https://police.example.com",
            allowed_domains=["police.example.com"],
            start_urls=["https://police.example.com/news/"],
            extractor_type="police_release_index",
            source_tier="official_police_open_data",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://police.example.com/1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://police.example.com/1",
            title="Police Release",
            published_at=None,
            candidate_type="crime_incident_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.source_quality == "official_police_open_data"

    def test_source_url_from_candidate(self, db):
        """ReviewItem source_url should come from candidate."""
        target = WebMonitorTarget(
            source_key="test",
            name="Test",
            source_type="news_only_context",
            base_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
            extractor_type="rss_or_news_listing",
            source_tier="news_only_context",
        )
        runner = CrawleeRunner(target, db)

        snapshot = SourceSnapshot(
            source_url="https://example.com/page1",
            fetched_at=datetime.now(timezone.utc),
            content_hash="hash",
        )
        db.add(snapshot)
        db.flush()

        candidate = ExtractedCandidate(
            source_url="https://example.com/page1",
            title="Test",
            published_at=None,
            candidate_type="news_context",
            summary="Summary",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.3,
        )

        review_item = runner._create_review_item(candidate, snapshot)

        assert review_item.source_url == "https://example.com/page1"


@pytest.fixture
def db():
    """Database session fixture."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
