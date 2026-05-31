"""Tests for Crawlee web monitor extractors.

These tests verify extractors create proper candidate records
with safety defaults applied.
"""

import pytest

from app.ingestion.web_monitor import (
    ExtractedCandidate,
    extract_from_page,
    get_extractor,
)
from app.ingestion.web_monitor.extractors import (
    CourtNewsExtractor,
    OpenDataLandingExtractor,
    PoliceReleaseExtractor,
    RSSNewsExtractor,
)


class TestExtractedCandidateSafety:
    """Test safety defaults for extracted candidates."""

    def test_candidate_defaults_to_low_confidence(self):
        """Candidate confidence should be clamped to max 0.5."""
        candidate = ExtractedCandidate(
            source_url="https://example.com/news",
            title="Test Article",
            published_at=None,
            summary="Test summary",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=[],
            confidence=0.8,  # Trying to set high confidence
        )

        # Should be clamped to 0.5
        assert candidate.confidence <= 0.5

    def test_candidate_has_verification_warning(self):
        """Candidate should have verification warning by default."""
        candidate = ExtractedCandidate(
            source_url="https://example.com/news",
            title="Test Article",
            published_at=None,
            summary="Test summary",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=[],  # Empty list
            confidence=0.3,
        )

        # Should have default warning added
        assert any("Crawled content" in w for w in candidate.warnings)

    def test_candidate_preserves_custom_warnings(self):
        """Candidate should preserve custom warnings."""
        candidate = ExtractedCandidate(
            source_url="https://example.com/news",
            title="Test Article",
            published_at=None,
            summary="Test summary",
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=["Custom warning"],
            confidence=0.3,
        )

        # Should have both custom and default warnings
        assert "Custom warning" in candidate.warnings
        assert any("Crawled content" in w for w in candidate.warnings)


class TestPoliceReleaseExtractor:
    """Test police release extractor."""

    def test_extracts_summary_from_content(self):
        """Should extract summary from HTML content."""
        extractor = PoliceReleaseExtractor()

        html = """
        <html>
        <body>
        <h1>Police News Release</h1>
        <p>On January 1, 2024, Saskatoon Police responded to a call
        in the Riversdale area regarding a suspicious person. Officers
        attended the scene and conducted an investigation. No arrests
        were made and the matter is under investigation.</p>
        </body>
        </html>
        """

        candidate = extractor.extract("https://police.example.com/news/1", html, "Police Release")

        assert candidate.candidate_type == "crime_incident_context"
        assert candidate.source_url == "https://police.example.com/news/1"
        assert "Saskatoon Police" in candidate.summary
        assert candidate.confidence <= 0.5

    def test_detects_location_hints(self):
        """Should try to extract location mentions."""
        extractor = PoliceReleaseExtractor()

        html = "<p>Incident occurred in Riversdale area of Saskatoon.</p>"

        candidate = extractor.extract("https://police.example.com/news/1", html)

        # Should have location hint
        assert candidate.location_text is not None

    def test_flags_private_address_patterns(self):
        """Should flag content with potential private addresses."""
        extractor = PoliceReleaseExtractor()

        html = "<p>Suspect located at 123 Main Street. Investigation ongoing.</p>"

        candidate = extractor.extract("https://police.example.com/news/1", html)

        # Should have warning about private address
        assert any("private address" in w.lower() for w in candidate.warnings)

    def test_flags_person_names(self):
        """Should flag content with many person names."""
        extractor = PoliceReleaseExtractor()

        # Content with many name-like patterns
        html = "<p>John Smith and Jane Doe met with Robert Johnson and Mary Williams."

        candidate = extractor.extract("https://police.example.com/news/1", html)

        # Should have warning about person names
        assert any("Person name" in w for w in candidate.warnings)


class TestCourtNewsExtractor:
    """Test court news extractor."""

    def test_extracts_court_related_content(self):
        """Should extract court-related content with higher confidence."""
        extractor = CourtNewsExtractor()

        html = """
        <html>
        <body>
        <h1>Federal Court Sentencing</h1>
        <p>Judge Smith presided over the sentencing hearing today.
        The defendant received a 24-month sentence. The court heard
        testimony from multiple witnesses.</p>
        </body>
        </html>
        """

        candidate = extractor.extract("https://court.example.com/news/1", html, "Court Sentencing")

        assert candidate.candidate_type == "court_update_context"
        assert "Judge" in candidate.summary or "court" in candidate.summary.lower()
        assert candidate.confidence > 0.3  # Higher confidence due to court terms

    def test_warns_when_no_court_terms(self):
        """Should warn when no court-related terms found."""
        extractor = CourtNewsExtractor()

        html = "<p>This is a general news article about community events.</p>"

        candidate = extractor.extract("https://example.com/news/1", html)

        # Should have warning about missing court terms
        assert any("court" in w.lower() for w in candidate.warnings)
        assert candidate.confidence < 0.3  # Lower confidence


class TestOpenDataLandingExtractor:
    """Test open data landing page extractor."""

    def test_extracts_portal_info(self):
        """Should extract open data portal information."""
        extractor = OpenDataLandingExtractor()

        html = """
        <html>
        <body>
        <h1>City of Saskatoon Open Data Portal</h1>
        <p>Welcome to our open data catalog. Browse datasets on crime,
        public safety, transportation, and more. Download CSV files
        for analysis.</p>
        <a href="/datasets">Browse Datasets</a>
        </body>
        </html>
        """

        candidate = extractor.extract("https://data.saskatoon.ca", html, "Open Data Portal")

        assert candidate.candidate_type == "news_context"
        assert "Open Data Portal" in candidate.title
        assert candidate.confidence <= 0.5


class TestRSSNewsExtractor:
    """Test RSS/news listing extractor."""

    def test_extracts_feed_info(self):
        """Should extract RSS/feed listing information."""
        extractor = RSSNewsExtractor()

        rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
        <title>Police News Feed</title>
        <item><title>News Item 1</title></item>
        <item><title>News Item 2</title></item>
        </channel>
        </rss>
        """

        candidate = extractor.extract("https://police.example.com/feed.xml", rss, "Police News Feed")

        assert candidate.candidate_type == "news_context"
        assert "News Feed" in candidate.title
        assert candidate.confidence <= 0.3  # Low confidence for listings


class TestExtractorRegistry:
    """Test extractor registry and lookup."""

    def test_get_extractor_returns_instance(self):
        """Should return extractor instance by type."""
        extractor = get_extractor("police_release_index")
        assert isinstance(extractor, PoliceReleaseExtractor)

    def test_get_extractor_unknown_type_raises(self):
        """Should raise ValueError for unknown extractor type."""
        with pytest.raises(ValueError, match="Unknown extractor type"):
            get_extractor("unknown_extractor_type")

    def test_extract_from_page_function(self):
        """extract_from_page should route to correct extractor."""
        html = "<p>Police responded to a call in the downtown area.</p>"

        candidate = extract_from_page(
            url="https://police.example.com/news/1",
            content=html,
            title="Police Release",
            extractor_type="police_release_index",
        )

        assert candidate.candidate_type == "crime_incident_context"
        assert candidate.source_url == "https://police.example.com/news/1"

    def test_all_registered_extractors(self):
        """All registered extractors should be instantiable."""
        from app.ingestion.web_monitor.extractors import EXTRACTORS

        for extractor_type in EXTRACTORS:
            extractor = get_extractor(extractor_type)
            assert extractor is not None
