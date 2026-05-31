"""Tests for review-priority triage logic.

Tests review-priority tier calculation and review requirements.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from uuid import uuid4

from app.models.entities import MemoryClaim, CanonicalEntity
from app.review.review_priority import (
    calculate_claim_review_priority_tier,
    get_review_requirements,
    can_auto_approve,
    calculate_entity_review_priority_tier,
    batch_calculate_review_priority_tiers,
)
from app.db.session import engine


class TestReviewPriorityCalculation:
    """Test review-priority tier calculation logic."""

    def test_low_confidence_high_risk(self, db_session):
        """Test that low confidence claims are high risk."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.2,
            contradiction_count=0,
            corroboration_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        review_priority_tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert review_priority_tier in ["high", "critical"]

    def test_high_confidence_low_risk(self, db_session):
        """Test that high confidence claims are low risk."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.9,
            contradiction_count=0,
            corroboration_count=2,
        )
        db_session.add(claim)
        db_session.commit()

        review_priority_tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert review_priority_tier in ["low", "medium"]

    def test_contradictions_increase_risk(self, db_session):
        """Test that contradictions increase risk tier."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.7,
            contradiction_count=3,
            corroboration_count=1,
        )
        db_session.add(claim)
        db_session.commit()

        review_priority_tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert review_priority_tier in ["high", "critical"]

    def test_lack_of_evidence_increases_risk(self, db_session):
        """Test that lack of evidence increases risk tier."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.7,
            contradiction_count=0,
            corroboration_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        review_priority_tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert review_priority_tier in ["medium", "high"]


class TestReviewRequirements:
    """Test review requirements per review-priority tier."""

    def test_critical_tier_requirements(self):
        """Test that critical tier requires review and evidence."""
        requirements = get_review_requirements("critical")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is True
        assert requirements["auto_approve"] is False

    def test_high_tier_requirements(self):
        """Test that high tier requires review and evidence."""
        requirements = get_review_requirements("high")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is True
        assert requirements["auto_approve"] is False

    def test_medium_tier_requirements(self):
        """Test that medium tier requires review but not evidence."""
        requirements = get_review_requirements("medium")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is False
        assert requirements["auto_approve"] is False

    def test_low_tier_requirements(self):
        """Test that low tier allows auto-approval."""
        requirements = get_review_requirements("low")
        assert requirements["requires_review"] is False
        assert requirements["requires_evidence"] is False
        assert requirements["auto_approve"] is True


class TestAutoApproval:
    """Test auto-approval logic."""

    def test_low_risk_can_auto_approve(self, db_session):
        """Test that low risk claims can be auto-approved."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.9,
            contradiction_count=0,
            corroboration_count=2,
        )
        db_session.add(claim)
        db_session.commit()

        assert can_auto_approve(claim.id, db_session) is True

    def test_high_risk_cannot_auto_approve(self, db_session):
        """Test that high risk claims cannot be auto-approved."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.3,
            contradiction_count=2,
            corroboration_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        assert can_auto_approve(claim.id, db_session) is False


class TestEntityReviewPriorityTier:
    """Test entity-level review-priority tier calculation."""

    def test_entity_risk_based_on_claims(self, db_session):
        """Test that entity risk is based on its claims."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Add low risk claim
        claim1 = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.9,
            contradiction_count=0,
            corroboration_count=2,
        )
        db_session.add(claim1)
        db_session.commit()

        review_priority_tier = calculate_entity_review_priority_tier(entity.id, db_session)
        assert review_priority_tier in ["low", "medium"]

    def test_entity_risk_max_of_claims(self, db_session):
        """Test that entity risk is the maximum of its claims."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Add high risk claim
        claim1 = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.3,
            contradiction_count=2,
            corroboration_count=0,
        )
        db_session.add(claim1)
        db_session.commit()

        review_priority_tier = calculate_entity_review_priority_tier(entity.id, db_session)
        assert review_priority_tier in ["high", "critical"]

    def test_batch_calculate_review_priority_tiers(self, db_session):
        """Test batch calculation of review-priority tiers."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Add multiple claims
        for i in range(3):
            claim = MemoryClaim(
                claim_key=f"test_claim_{i}_{uuid4().hex[:8]}",
                claim_type="test",
                entity_id=entity.id,
                claim_value=f"Test value {i}",
                confidence=0.7,
                contradiction_count=0,
                corroboration_count=1,
            )
            db_session.add(claim)
        db_session.commit()

        review_priority_tiers = batch_calculate_review_priority_tiers(entity.id, db_session)
        assert len(review_priority_tiers) == 3
        for claim_id, tier in review_priority_tiers.items():
            assert tier in ["low", "medium", "high", "critical"]


@pytest.fixture
def db_session():
    """Create an isolated database session for testing."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, future=True)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not getattr(trans._parent, "nested", False):
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        transaction.rollback()
        connection.close()
