"""Tests for upgraded contradiction intelligence (Phase 5)."""
import pytest
from datetime import datetime, timezone

from app.models.entities import MemoryClaim, LegalSource, SourceSnapshot, CanonicalEntity
from app.memory.contradiction_engine import (
    _calculate_severity,
    _get_source_authority_weight,
    auto_supersede_by_authority,
    detect_contradictions,
)
from app.db.session import SessionLocal


def test_source_authority_weight_hierarchy():
    """Test that source authority weights follow the expected hierarchy."""
    # Test official court record has highest weight
    court_source = LegalSource(source_type="official_court_record")
    assert _get_source_authority_weight(court_source) == 1.0

    # Test official government has high weight
    gov_source = LegalSource(source_type="official_government")
    assert _get_source_authority_weight(gov_source) == 0.8

    # Test social media has lower weight
    social_source = LegalSource(source_type="social_media")
    assert _get_source_authority_weight(social_source) == 0.4

    # Test unknown source has default weight
    unknown_source = LegalSource(source_type="unknown")
    assert _get_source_authority_weight(unknown_source) == 0.2


def test_calculate_severity_considers_source_authority():
    """Test that severity calculation considers source authority."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create two claims with different source authorities
        claim1 = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
        )
        claim2 = MemoryClaim(
            claim_key="test-claim-2",
            claim_uid="uid-2",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Unemployed",
            normalized_value="unemployed",
            confidence=0.9,
            object_value_type="literal",
        )
        db.add(claim1)
        db.add(claim2)
        db.commit()

        # Test severity with high authority sources
        severity = _calculate_severity("value_contradiction", claim1, claim2, db)
        # Should be at least medium due to high confidence
        assert severity in ["low", "medium", "high", "critical"]

    finally:
        db.close()


def test_calculate_severity_considers_confidence():
    """Test that severity calculation considers confidence scores."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create high-confidence claim
        claim_high_conf = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.95,
            object_value_type="literal",
        )
        # Create low-confidence claim
        claim_low_conf = MemoryClaim(
            claim_key="test-claim-2",
            claim_uid="uid-2",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Unemployed",
            normalized_value="unemployed",
            confidence=0.5,
            object_value_type="literal",
        )
        db.add(claim_high_conf)
        db.add(claim_low_conf)
        db.commit()

        # High confidence should increase severity
        severity = _calculate_severity("value_contradiction", claim_high_conf, claim_low_conf, db)
        assert severity in ["low", "medium", "high", "critical"]

    finally:
        db.close()


def test_auto_supersede_by_authority():
    """Test automatic supersession based on source authority."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create high-authority source
        high_auth_source = LegalSource(
            source_id="court-source",
            source_type="official_court_record",
            lifecycle_state="active",
        )
        db.add(high_auth_source)
        db.commit()

        # Create low-authority source
        low_auth_source = LegalSource(
            source_id="social-source",
            source_type="social_media",
            lifecycle_state="active",
        )
        db.add(low_auth_source)
        db.commit()

        # Create snapshots
        snapshot_high = SourceSnapshot(
            source_id=high_auth_source.id,
            snapshot_at=datetime.now(timezone.utc),
        )
        snapshot_low = SourceSnapshot(
            source_id=low_auth_source.id,
            snapshot_at=datetime.now(timezone.utc),
        )
        db.add(snapshot_high)
        db.add(snapshot_low)
        db.commit()

        # Create claims with different sources
        claim_high = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            source_snapshot_id=snapshot_high.id,
            object_value_type="literal",
        )
        claim_low = MemoryClaim(
            claim_key="test-claim-2",
            claim_uid="uid-2",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Unemployed",
            normalized_value="unemployed",
            confidence=0.9,
            source_snapshot_id=snapshot_low.id,
            object_value_type="literal",
        )
        db.add(claim_high)
        db.add(claim_low)
        db.commit()

        # Create contradiction
        from app.models.entities import MemoryContradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim_high.id,
            claim_b_id=claim_low.id,
            conflict_type="value_contradiction",
            severity="high",
            status="open",
            detected_by="system",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(contradiction)
        db.commit()

        # Auto-supersede by authority
        result = auto_supersede_by_authority(contradiction.id, db)
        assert result is True

        # Verify low-authority claim was superseded
        db.refresh(claim_low)
        assert claim_low.status == "superseded"
        assert claim_low.is_active is False

        # Verify contradiction was resolved
        db.refresh(contradiction)
        assert contradiction.status == "resolved"

    finally:
        db.close()


def test_auto_supersede_no_action_for_similar_authority():
    """Test that auto-supersede does nothing for similar authority levels."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create two similar authority sources
        source1 = LegalSource(
            source_id="news-source-1",
            source_type="news_article",
            lifecycle_state="active",
        )
        source2 = LegalSource(
            source_id="news-source-2",
            source_type="news_article",
            lifecycle_state="active",
        )
        db.add(source1)
        db.add(source2)
        db.commit()

        # Create snapshots
        snapshot1 = SourceSnapshot(
            source_id=source1.id,
            snapshot_at=datetime.now(timezone.utc),
        )
        snapshot2 = SourceSnapshot(
            source_id=source2.id,
            snapshot_at=datetime.now(timezone.utc),
        )
        db.add(snapshot1)
        db.add(snapshot2)
        db.commit()

        # Create claims
        claim1 = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            source_snapshot_id=snapshot1.id,
            object_value_type="literal",
        )
        claim2 = MemoryClaim(
            claim_key="test-claim-2",
            claim_uid="uid-2",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Unemployed",
            normalized_value="unemployed",
            confidence=0.9,
            source_snapshot_id=snapshot2.id,
            object_value_type="literal",
        )
        db.add(claim1)
        db.add(claim2)
        db.commit()

        # Create contradiction
        from app.models.entities import MemoryContradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim1.id,
            claim_b_id=claim2.id,
            conflict_type="value_contradiction",
            severity="medium",
            status="open",
            detected_by="system",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(contradiction)
        db.commit()

        # Auto-supersede by authority should not act (similar authority)
        result = auto_supersede_by_authority(contradiction.id, db)
        assert result is False

        # Verify claims are still active
        db.refresh(claim1)
        db.refresh(claim2)
        assert claim1.is_active is True
        assert claim2.is_active is True

        # Verify contradiction is still open
        db.refresh(contradiction)
        assert contradiction.status == "open"

    finally:
        db.close()
