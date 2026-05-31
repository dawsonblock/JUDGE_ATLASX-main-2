"""Test that Crawlee-generated review items have correct safety defaults."""

import pytest
from datetime import datetime, timezone
from app.models.entities import ReviewItem, SourceSnapshot, IngestionRun
from app.ingestion.web_monitor.crawlee_runner import CrawleeRunner
from app.ingestion.web_monitor.source_targets import SASKATOON_POLICE_NEWS_TARGET


def test_crawlee_review_items_safety_defaults(db_session):
    """Test that Crawlee review items have correct safety defaults.

    All Crawlee-created review items must have:
    - status="pending" (never auto-publish)
    - public_visibility absent or False
    - confidence <= 0.5 (hard cap)
    - publish_recommendation="review_required"
    """
    # Create mock ingestion run
    run = IngestionRun(
        source_name="test_crawlee",
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    # Create mock snapshot
    snapshot = SourceSnapshot(
        source_url="https://saskatoonpolice.ca/test",
        fetched_at=datetime.now(timezone.utc),
        raw_content="test content",
        content_hash="test_hash",
        extracted_text="extracted test",
        http_status=200,
        content_type="text/html",
        error_message=None,
        ingestion_run_id=run.id,
    )
    db_session.add(snapshot)
    db_session.flush()

    # Create runner
    runner = CrawleeRunner(SASKATOON_POLICE_NEWS_TARGET, db_session)

    # Create mock extracted candidate
    from app.ingestion.web_monitor.extractors import ExtractedCandidate

    candidate = ExtractedCandidate(
        candidate_type="crime_incident",
        title="Test Incident",
        summary="A test incident summary",
        source_url="https://saskatoonpolice.ca/test",
        location_text="Saskatoon, SK",
        published_at=datetime.now(timezone.utc),
        confidence=0.8,  # Should be capped to 0.5
        entities=[],
        warnings=["contains_address"],
    )

    # Create review item via runner
    review_item = runner._create_review_item(candidate, snapshot, run.id)
    db_session.add(review_item)
    db_session.flush()

    # Assert safety defaults
    assert review_item.status == "pending", "All crawled items must be pending review"
    assert (
        review_item.public_visibility != True
    ), "Crawled items must not be public by default"
    assert (
        review_item.confidence <= 0.5
    ), f"Confidence must be capped at 0.5, got {review_item.confidence}"
    assert (
        review_item.publish_recommendation == "review_required"
    ), "Must require human review"
    assert (
        review_item.privacy_status == "needs_review"
    ), "Address warning triggers privacy review"
    assert review_item.source_snapshot_id == snapshot.id, "Must link to source snapshot"


def test_crawlee_review_item_confidence_capped(db_session):
    """Test that high confidence scores are capped to 0.5."""
    run = IngestionRun(
        source_name="test_confidence",
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    snapshot = SourceSnapshot(
        source_url="https://example.com/test",
        fetched_at=datetime.now(timezone.utc),
        raw_content="test",
        content_hash="hash",
        extracted_text="extracted",
        http_status=200,
        content_type="text/html",
        ingestion_run_id=run.id,
    )
    db_session.add(snapshot)
    db_session.flush()

    runner = CrawleeRunner(SASKATOON_POLICE_NEWS_TARGET, db_session)

    from app.ingestion.web_monitor.extractors import ExtractedCandidate

    # Test with very high confidence
    candidate = ExtractedCandidate(
        candidate_type="court_event",
        title="High Confidence Event",
        summary="Test",
        source_url="https://example.com/test",
        location_text="Test Location",
        published_at=datetime.now(timezone.utc),
        confidence=0.99,  # Extremely high
        entities=[],
        warnings=[],
    )

    review_item = runner._create_review_item(candidate, snapshot, run.id)

    assert (
        review_item.confidence == 0.5
    ), "Confidence must be capped at 0.5, regardless of input"


def test_crawlee_publish_recommendation_in_constants(db_session):
    """Test that publish_recommendation value is a valid member of AI_PUBLISH_RECOMMENDATIONS."""
    from app.services.constants import AI_PUBLISH_RECOMMENDATIONS

    run = IngestionRun(
        source_name="test_constants_check",
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    snapshot = SourceSnapshot(
        source_url="https://example.com/constants-check",
        fetched_at=datetime.now(timezone.utc),
        raw_content="test",
        content_hash="hash_constants",
        extracted_text="extracted",
        http_status=200,
        content_type="text/html",
        ingestion_run_id=run.id,
    )
    db_session.add(snapshot)
    db_session.flush()

    runner = CrawleeRunner(SASKATOON_POLICE_NEWS_TARGET, db_session)

    from app.ingestion.web_monitor.extractors import ExtractedCandidate

    candidate = ExtractedCandidate(
        candidate_type="crime_incident",
        title="Constants Test",
        summary="Test",
        source_url="https://example.com/constants-check",
        location_text="Test Location",
        published_at=datetime.now(timezone.utc),
        confidence=0.4,
        entities=[],
        warnings=[],
    )

    review_item = runner._create_review_item(candidate, snapshot, run.id)

    assert review_item.publish_recommendation in AI_PUBLISH_RECOMMENDATIONS, (
        f"publish_recommendation '{review_item.publish_recommendation}' "
        f"must be a member of AI_PUBLISH_RECOMMENDATIONS {AI_PUBLISH_RECOMMENDATIONS}"
    )


# ── _robots_allowed fail-closed contract ─────────────────────────────────────


class TestRobotsAllowedFailClosed:
    """_robots_allowed must return False whenever the robots.txt cannot be
    verified (network errors, malformed content, timeouts)."""

    def test_network_error_returns_false(self) -> None:
        """A URLError / OSError during robots.txt fetch must block the URL."""
        from unittest.mock import patch
        import urllib.error
        from app.ingestion.web_monitor.crawlee_runner import _robots_allowed

        with patch(
            "app.ingestion.web_monitor.crawlee_runner.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            assert _robots_allowed("https://example.com/page") is False

    def test_timeout_returns_false(self) -> None:
        """A socket timeout must block the URL (fail-closed)."""
        from unittest.mock import patch
        import socket
        from app.ingestion.web_monitor.crawlee_runner import _robots_allowed

        with patch(
            "app.ingestion.web_monitor.crawlee_runner.urllib.request.urlopen",
            side_effect=socket.timeout("timed out"),
        ):
            assert _robots_allowed("https://example.com/page") is False

    def test_malformed_robots_txt_returns_false(self) -> None:
        """If urlopen succeeds but the content is gibberish, must block."""
        from unittest.mock import MagicMock, patch
        from app.ingestion.web_monitor.crawlee_runner import _robots_allowed

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"\xff\xfe\x00not valid utf-8 robots"

        # RobotFileParser.parse will not raise on malformed content, but
        # can_fetch will conservatively return False for unknown states.
        # We patch parse to raise to simulate truly unparseable content.
        with (
            patch(
                "app.ingestion.web_monitor.crawlee_runner.urllib.request.urlopen",
                return_value=mock_resp,
            ),
            patch(
                "app.ingestion.web_monitor.crawlee_runner.RobotFileParser.parse",
                side_effect=ValueError("malformed"),
            ),
        ):
            assert _robots_allowed("https://example.com/page") is False

    def test_explicit_disallow_returns_false(self) -> None:
        """A valid robots.txt that disallows the user-agent must block."""
        from unittest.mock import MagicMock, patch
        from app.ingestion.web_monitor.crawlee_runner import _robots_allowed

        robots_content = b"User-agent: *\nDisallow: /\n"
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = robots_content

        with patch(
            "app.ingestion.web_monitor.crawlee_runner.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            assert _robots_allowed("https://example.com/some-path") is False

    def test_explicit_allow_returns_true(self) -> None:
        """A valid robots.txt that permits the user-agent must allow."""
        from unittest.mock import MagicMock, patch
        from app.ingestion.web_monitor.crawlee_runner import _robots_allowed

        robots_content = b"User-agent: *\nAllow: /\n"
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = robots_content

        with patch(
            "app.ingestion.web_monitor.crawlee_runner.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            assert _robots_allowed("https://example.com/some-path") is True
