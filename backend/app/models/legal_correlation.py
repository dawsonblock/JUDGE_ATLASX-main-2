"""Legal correlation model for storing correlation hypotheses.

This model provides database backing for legal correlations detected
by the correlation engine. Correlations are hypotheses, not verdicts,
and require review before being used in publication decisions.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LegalCorrelation(Base):
    """Legal correlation hypothesis.

    Correlations are relationships detected between legal events, claims,
    and entities. They are hypotheses that require review before being
    used in publication decisions.
    """

    __tablename__ = "legal_correlations"

    # Core identification
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    correlation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # Linked items (stored as JSON arrays of IDs)
    event_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of event IDs
    claim_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of claim IDs
    evidence_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # JSON array of evidence IDs

    # Quality indicators
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0", default=0.0)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high

    # Review status
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="needs_review", index=True
    )

    # Metadata
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
        Index("idx_legal_correlations_type", "correlation_type"),
        Index("idx_legal_correlations_review_status", "review_status"),
        Index("idx_legal_correlations_risk_level", "risk_level"),
        Index("idx_legal_correlations_confidence", "confidence"),
        Index(
            "idx_legal_correlations_type_review",
            "correlation_type",
            "review_status",
        ),
    )