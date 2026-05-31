"""GeoLegalEvent model for normalized map-facing event layer.

This model provides the database backing for the GeoLegalEvent schema,
representing materialized events from evidence-backed claims that are
ready for map rendering.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GeoLegalEvent(Base):
    """Normalized legal event for map rendering.

    The map never renders raw scraped data directly. It renders only GeoLegalEvent
    rows derived from evidence-backed claims that have passed the publication gate.
    """

    __tablename__ = "geo_legal_events"

    # Core identification
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # Content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Temporal
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Geographic
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    province: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str] = mapped_column(String(80), nullable=False)

    # Provenance links (stored as JSON arrays of IDs)
    source_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of source IDs
    evidence_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of evidence IDs
    claim_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of claim IDs

    # Quality indicators
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    confidence_label: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    publish_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Classification
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)  # JSON array of tags
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)  # JSON object

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_geo_legal_events_event_type", "event_type"),
        Index("idx_geo_legal_events_review_status", "review_status"),
        Index("idx_geo_legal_events_publish_status", "publish_status"),
        Index("idx_geo_legal_events_jurisdiction", "jurisdiction"),
        Index("idx_geo_legal_events_country", "country"),
        Index("idx_geo_legal_events_created_at", "created_at"),
        Index(
            "idx_geo_legal_events_type_review_publish",
            "event_type",
            "review_status",
            "publish_status",
        ),
        Index("idx_geo_legal_events_review_publish", "review_status", "publish_status"),
    )