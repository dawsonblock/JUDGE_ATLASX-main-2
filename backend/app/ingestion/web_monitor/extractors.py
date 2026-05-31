"""Narrow extractors for specific web page types.

Extractors are designed to extract structured data from known page types.
They do NOT perform open-ended AI scraping - only extract what is clearly
present on the page with low confidence for review.

All extracted items go to pending_review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class ExtractedCandidate:
    """A candidate record extracted from a web page.

    All candidates default to pending_review and low confidence.
    """

    source_url: str
    title: str | None
    published_at: datetime | None
    summary: str
    candidate_type: str  # "news_context" | "crime_incident_context" | "court_update_context"
    location_text: str | None
    entities: list[dict]
    warnings: list[str]
    confidence: float  # 0.0-1.0, max 0.5 for crawled content

    def __post_init__(self):
        """Enforce safety defaults."""
        # Clamp confidence to max 0.5 for crawled content
        self.confidence = min(self.confidence, 0.5)

        # Ensure warnings list
        if self.warnings is None:
            self.warnings = []

        # Add default warning for crawled content
        if "Crawled content - requires verification" not in self.warnings:
            self.warnings.append("Crawled content - requires verification")


class Extractor(Protocol):
    """Protocol for page extractors."""

    def extract(self, url: str, content: str, title: str | None = None) -> ExtractedCandidate:
        """Extract candidate data from page content.

        Args:
            url: Page URL
            content: Page HTML/text content
            title: Page title if available

        Returns:
            ExtractedCandidate with extracted fields
        """
        ...


class PoliceReleaseExtractor:
    """Extractor for police news release pages."""

    def extract(self, url: str, content: str, title: str | None = None) -> ExtractedCandidate:
        """Extract from police release page."""
        warnings = []
        location_text = None

        # Simple extraction - first paragraph as summary
        summary = self._extract_summary(content)

        # Try to find location mentions
        location_text = self._extract_location_hint(content)

        # Check for concerning patterns
        if self._has_private_address(content):
            warnings.append("Possible private address mention - requires review")

        if self._has_person_name(content):
            warnings.append("Person name detected - verify not private individual")

        return ExtractedCandidate(
            source_url=url,
            title=title or "Police Release",
            published_at=None,  # Would need date extraction
            summary=summary[:500],
            candidate_type="crime_incident_context",
            location_text=location_text,
            entities=[],
            warnings=warnings,
            confidence=0.3,  # Low confidence for crawled content
        )

    def _extract_summary(self, content: str) -> str:
        """Extract first substantial paragraph."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", content)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Return first 500 chars
        return text[:500]

    def _extract_location_hint(self, content: str) -> str | None:
        """Try to find location mentions."""
        # Simple pattern matching for city/neighborhood names
        # This is intentionally narrow - just a hint for review
        location_patterns = [
            r"in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)",
        ]

        for pattern in location_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _has_private_address(self, content: str) -> bool:
        """Check for potential private address patterns."""
        # Look for street address patterns
        address_patterns = [
            r"\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Court|Ct)",
            r"(?:residence|home address|private residence)",
        ]
        for pattern in address_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False

    def _has_person_name(self, content: str) -> bool:
        """Check for potential person names."""
        # Simple pattern - this is intentionally conservative
        # Matches "John Smith" or "J. Smith" patterns
        name_pattern = r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"
        matches = re.findall(name_pattern, content)
        # If we find more than 3 name-like patterns, flag it
        return len(matches) > 3


class CourtNewsExtractor:
    """Extractor for court announcement/news pages."""

    def extract(self, url: str, content: str, title: str | None = None) -> ExtractedCandidate:
        """Extract from court news page."""
        warnings = []

        summary = self._extract_summary(content)

        # Check for court-related terms
        has_court_terms = any(
            term in content.lower()
            for term in ["court", "judge", "sentencing", "hearing", "trial", "docket"]
        )

        if not has_court_terms:
            warnings.append("No clear court-related terms found")

        return ExtractedCandidate(
            source_url=url,
            title=title or "Court News",
            published_at=None,
            summary=summary[:500],
            candidate_type="court_update_context",
            location_text=None,
            entities=[],
            warnings=warnings,
            confidence=0.4 if has_court_terms else 0.2,
        )

    def _extract_summary(self, content: str) -> str:
        """Extract first substantial paragraph."""
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]


class OpenDataLandingExtractor:
    """Extractor for city/police open data portal landing pages."""

    def extract(self, url: str, content: str, title: str | None = None) -> ExtractedCandidate:
        """Extract from open data landing page."""
        warnings = []

        summary = self._extract_summary(content)

        # Check for data/catalog links
        if re.search(r"dataset|data|catalog|download", content, re.IGNORECASE):
            summary = f"Open data portal with datasets: {summary[:200]}"

        return ExtractedCandidate(
            source_url=url,
            title=title or "Open Data Portal",
            published_at=None,
            summary=summary[:500],
            candidate_type="news_context",  # Just context, not actual data
            location_text=None,
            entities=[],
            warnings=warnings,
            confidence=0.3,
        )

    def _extract_summary(self, content: str) -> str:
        """Extract first substantial paragraph."""
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]


class RSSNewsExtractor:
    """Extractor for RSS feeds and news listing pages."""

    def extract(self, url: str, content: str, title: str | None = None) -> ExtractedCandidate:
        """Extract from RSS/news listing."""
        warnings = []

        # For RSS/listings, we mostly want to acknowledge we found it
        # Actual item extraction would happen on individual pages
        summary = f"News/RSS feed found at {url}"
        if title:
            summary = f"News source: {title}"

        return ExtractedCandidate(
            source_url=url,
            title=title or "News Feed",
            published_at=None,
            summary=summary[:500],
            candidate_type="news_context",
            location_text=None,
            entities=[],
            warnings=warnings,
            confidence=0.2,  # Very low - just a listing
        )


# Registry of extractors by type
EXTRACTORS: dict[str, type] = {
    "police_release_index": PoliceReleaseExtractor,
    "police_release_detail": PoliceReleaseExtractor,
    "court_news_index": CourtNewsExtractor,
    "court_news_detail": CourtNewsExtractor,
    "city_open_data_landing_page": OpenDataLandingExtractor,
    "rss_or_news_listing": RSSNewsExtractor,
}


def get_extractor(extractor_type: str) -> Extractor:
    """Get extractor instance by type.

    Args:
        extractor_type: Type of extractor to get

    Returns:
        Extractor instance

    Raises:
        ValueError: If extractor_type is not registered
    """
    if extractor_type not in EXTRACTORS:
        raise ValueError(f"Unknown extractor type: {extractor_type}")
    return EXTRACTORS[extractor_type]()


def extract_from_page(
    url: str,
    content: str,
    title: str | None,
    extractor_type: str,
) -> ExtractedCandidate:
    """Extract candidate from page using appropriate extractor.

    Args:
        url: Page URL
        content: Page content
        title: Page title
        extractor_type: Type of extractor to use

    Returns:
        ExtractedCandidate with safety defaults applied
    """
    extractor = get_extractor(extractor_type)
    return extractor.extract(url, content, title)
