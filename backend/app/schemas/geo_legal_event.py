"""GeoLegalEvent schema for normalized map-facing event layer.

This schema provides one normalized object that every map layer can render.
It abstracts over the underlying data models (Event, CrimeIncident, MemoryClaim, etc.)
to provide a consistent interface for the live map API.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from app.policies.public_status import (
    PUBLIC_ADMIN_ONLY,
    PUBLIC_BLOCKED,
    PUBLIC_PRIVATE,
    PUBLIC_REDACTED,
    PUBLIC_SAFE,
)


class GeoLegalEvent(BaseModel):
    """Normalized legal event for map rendering.

    The map never renders raw scraped data directly. It renders only GeoLegalEvent
    rows derived from evidence-backed claims.
    """

    # Core identification
    id: str
    event_type: str

    # Content
    title: str
    description: str | None = None

    # Location
    lat: float | None = None
    lng: float | None = None
    location_name: str | None = None

    # Temporal
    occurred_at: datetime | None = None
    published_at: datetime | None = None

    # Geographic
    jurisdiction: str
    province: str | None = None
    country: str

    # Provenance links
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)

    # Quality indicators
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str  # e.g., "high", "medium", "low"
    review_status: str
    publish_status: str

    # Classification
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value):
        return value or []

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value):
        return value or {}

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {value}")
        return value

    @field_validator("review_status")
    @classmethod
    def _validate_review_status(cls, value: str) -> str:
        if value not in REVIEW_STATUSES:
            raise ValueError(f"Invalid review_status: {value}")
        return value

    @field_validator("publish_status")
    @classmethod
    def _validate_publish_status(cls, value: str) -> str:
        if value not in PUBLISH_STATUSES:
            raise ValueError(f"Invalid publish_status: {value}")
        return value

    @field_validator("confidence_label")
    @classmethod
    def _validate_confidence_label(cls, value: str) -> str:
        allowed = set(CONFIDENCE_LABELS.values())
        if value not in allowed:
            raise ValueError(f"Invalid confidence_label: {value}")
        return value


# Event types
EVENT_TYPES = [
    "court_event",
    "judge_event",
    "crime_event",
    "police_release",
    "news_event",
    "legislation_event",
    "statistical_event",
    "correction_event",
    "contradiction_event",
]

# Review statuses
REVIEW_STATUSES = [
    "raw",
    "parsed",
    "needs_review",
    "approved",
    "rejected",
    "superseded",
]

# Publish statuses
PUBLISH_STATUSES = [
    PUBLIC_PRIVATE,
    PUBLIC_ADMIN_ONLY,
    PUBLIC_SAFE,
    PUBLIC_REDACTED,
    PUBLIC_BLOCKED,
]

# Confidence labels
CONFIDENCE_LABELS = {
    (0.9, 1.0): "very_high",
    (0.7, 0.9): "high",
    (0.5, 0.7): "medium",
    (0.3, 0.5): "low",
    (0.0, 0.3): "very_low",
}


def get_confidence_label(confidence: float) -> str:
    """Get the confidence label for a given confidence score."""
    for (min_conf, max_conf), label in CONFIDENCE_LABELS.items():
        if min_conf <= confidence <= max_conf:
            return label
    return "very_low"
