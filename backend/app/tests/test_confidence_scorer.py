"""Tests for confidence scoring (Phase 6).

Tests confidence calculation based on source quality, corroboration,
contradiction penalty, and extraction model reliability.
"""

import pytest
from uuid import uuid4

from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot
from app.memory.confidence_scorer import (
    calculate_claim_confidence,
    recalculate_claim_confidence,
    batch_recalculate_confidence,
)
from app.db.session import SessionLocal


class TestConfidenceCalculation:
    """Test confidence scoring logic."""

    def test_source_quality_score(self, db_session):
        """Test confidence score based on source quality."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        # Test with primary source
        suffix = uuid4().hex[:8]
        claim = MemoryClaim(
            claim_key=f"test_claim_1_{suffix}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            extraction_model="gpt4",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id=f"test_source_{suffix}",
            snapshot_hash=f"test_hash_{suffix}",
            content="Test content",
            source_quality="primary",
        )
        db_session.add(snapshot)
        db_session.commit()

        evidence = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            evidence_checksum="hash",
            support_type="supports",
            confidence=0.8,
        )
        db_session.add(evidence)
        db_session.commit()

        confidence = calculate_claim_confidence(claim.id, db_session)
        assert confidence > 0.7  # High confidence for primary source

    def test_corroboration_bonus(self, db_session):
        """Test corroboration bonus for multiple supporting sources."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            extraction_model="gpt4",
        )
        db_session.add(claim)
        db_session.commit()

        # Add multiple supporting sources
        for i in range(3):
            suffix = uuid4().hex[:8]
            snapshot = SourceSnapshot(
                source_id=f"test_source_{i}_{suffix}",
                snapshot_hash=f"hash_{i}_{suffix}",
                content=f"Test content {i}",
                source_quality="verified",
            )
            db_session.add(snapshot)
            db_session.commit()

            evidence = MemoryEvidenceLink(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                evidence_checksum=f"evidence_hash_{i}",
                support_type="supports",
                confidence=0.8,
            )
            db_session.add(evidence)
            db_session.commit()

        confidence = calculate_claim_confidence(claim.id, db_session)
        # Should have corroboration bonus
        assert confidence > 0.5

    def test_contradiction_penalty(self, db_session):
        """Test penalty for contradictions."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            extraction_model="gpt4",
            contradiction_count=2,
        )
        db_session.add(claim)
        db_session.commit()

        confidence = calculate_claim_confidence(claim.id, db_session)
        # Should have contradiction penalty
        assert confidence < 0.8

    def test_model_reliability_weighting(self, db_session):
        """Test extraction model reliability weighting."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        # Test with high reliability model
        claim1 = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            extraction_model="human_verified",
        )
        db_session.add(claim1)
        db_session.commit()

        confidence1 = calculate_claim_confidence(claim1.id, db_session)

        # Test with low reliability model
        claim2 = MemoryClaim(
            claim_key=f"test_claim_2_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            extraction_model="legacy",
        )
        db_session.add(claim2)
        db_session.commit()

        confidence2 = calculate_claim_confidence(claim2.id, db_session)

        # Human verified should have higher confidence
        assert confidence1 > confidence2


class TestConfidenceRecalculation:
    """Test confidence recalculation triggers."""

    def test_recalculate_single_claim(self, db_session):
        """Test recalculation of a single claim."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            confidence=0.5,
        )
        db_session.add(claim)
        db_session.commit()

        initial_confidence = claim.confidence
        assert recalculate_claim_confidence(claim.id, db_session) is True

        db_session.refresh(claim)
        # Confidence should be recalculated
        assert claim.confidence != initial_confidence

    def test_batch_recalculate_entity_claims(self, db_session):
        """Test batch recalculation for entity claims."""
        entity = db_session.query(MemoryClaim).first()
        if not entity:
            pytest.skip("No existing claim found")

        # Create multiple claims
        for i in range(3):
            claim = MemoryClaim(
                claim_key=f"test_claim_{i}_{uuid4().hex[:8]}",
                claim_type="test",
                entity_id=1,
                claim_value=f"Test value {i}",
                confidence=0.5,
            )
            db_session.add(claim)
        db_session.commit()

        updated_count = batch_recalculate_confidence(1, db_session)
        assert updated_count >= 3


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
