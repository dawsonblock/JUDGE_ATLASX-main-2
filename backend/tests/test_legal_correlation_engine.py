"""Tests for legal correlation engine."""
import pytest
from app.services.legal_correlation_engine import (
    LegalCorrelation,
    LegalCorrelationEngine,
)


def test_legal_correlation_creation():
    """Test creating a LegalCorrelation instance."""
    correlation = LegalCorrelation(
        correlation_type="same_event_multiple_sources",
        event_ids=["event-1", "event-2"],
        claim_ids=[],
        evidence_ids=[],
        confidence=0.8,
        explanation="Event reported by 2 different sources",
        risk_level="low",
        review_status="auto_approved",
    )

    assert correlation.correlation_type == "same_event_multiple_sources"
    assert len(correlation.event_ids) == 2
    assert correlation.confidence == 0.8
    assert correlation.risk_level == "low"
    assert correlation.review_status == "auto_approved"


def test_legal_correlation_to_dict():
    """Test converting LegalCorrelation to dictionary."""
    correlation = LegalCorrelation(
        correlation_type="duplicate_incident_report",
        event_ids=["incident-1", "incident-2"],
        claim_ids=[],
        evidence_ids=[],
        confidence=0.6,
        explanation="Similar incident reports within 7 days",
        risk_level="low",
        review_status="auto_approved",
    )

    correlation_dict = correlation.to_dict()

    assert correlation_dict["correlation_type"] == "duplicate_incident_report"
    assert correlation_dict["confidence"] == 0.6
    assert "id" in correlation_dict
    assert "created_at" in correlation_dict


def test_legal_correlation_engine_initialization():
    """Test LegalCorrelationEngine initialization."""
    engine = LegalCorrelationEngine()

    assert len(engine.correlation_types) == 8
    assert "same_event_multiple_sources" in engine.correlation_types
    assert "contradictory_source_claims" in engine.correlation_types
    assert "stale_update_detected" in engine.correlation_types


def test_legal_correlation_engine_detect_correlations_empty_db():
    """Test correlation detection with empty database."""
    from app.db.session import SessionLocal

    engine = LegalCorrelationEngine()
    db = SessionLocal()

    try:
        correlations = engine.detect_correlations(
            db,
            correlation_types=["same_event_multiple_sources"],
            confidence_threshold=0.5,
        )

        # Should return empty list for empty database
        assert isinstance(correlations, list)
    finally:
        db.close()


def test_legal_correlation_sensitive_review_status():
    """Test that sensitive correlations require review."""
    correlation = LegalCorrelation(
        correlation_type="same_person_multiple_cases",
        event_ids=[],
        claim_ids=["claim-1", "claim-2"],
        evidence_ids=[],
        confidence=0.7,
        explanation="Person appears in multiple cases",
        risk_level="medium",
        review_status="needs_review",  # Should require review
    )

    assert correlation.review_status == "needs_review"
    assert correlation.risk_level == "medium"


def test_legal_correlation_high_risk():
    """Test high-risk correlation detection."""
    correlation = LegalCorrelation(
        correlation_type="contradictory_source_claims",
        event_ids=[],
        claim_ids=["claim-1", "claim-2"],
        evidence_ids=[],
        confidence=0.9,
        explanation="Multiple contradictory claims from same source",
        risk_level="high",
        review_status="needs_review",
    )

    assert correlation.risk_level == "high"
    assert correlation.confidence == 0.9
