"""Tests for review-priority tier logic (Phase 2).

Tests review-priority tier calculation with correct thresholds and rules.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from uuid import uuid4

from app.models.entities import MemoryClaim, CanonicalEntity
from app.review.review_priority import (
    calculate_claim_review_priority_tier,
    calculate_entity_review_priority_tier,
    can_auto_approve,
    get_review_requirements,
)
from app.db.session import engine


class TestReviewPriorityThresholds:
    """Test review-priority tier threshold logic."""

    def test_official_statute_update_low_risk(self, db_session):
        """Test official statute update results in low risk tier."""
        entity = CanonicalEntity(
            entity_type="statute",
            canonical_name="Criminal Code Section 123",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_1_{uuid4().hex[:8]}",
            claim_type="statute_text",
            entity_id=entity.id,
            claim_value="Section 123 text",
            confidence=0.95,
            contradiction_count=0,
            corroboration_count=5,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert tier == "low"

    def test_court_decision_extraction_medium_risk(self, db_session):
        """Test court decision extraction results in medium risk tier."""
        entity = CanonicalEntity(
            entity_type="case",
            canonical_name="R v Smith",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_2_{uuid4().hex[:8]}",
            claim_type="case_outcome",
            entity_id=entity.id,
            claim_value="Convicted",
            confidence=0.75,
            contradiction_count=0,
            corroboration_count=2,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert tier == "medium"

    def test_unresolved_contradiction_high_risk(self, db_session):
        """Test unresolved contradiction results in high risk tier."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_3_{uuid4().hex[:8]}",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            confidence=0.80,
            contradiction_count=3,  # Unresolved contradictions
            corroboration_count=2,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert tier == "high"

    def test_criminal_allegation_named_person_critical_risk(self, db_session):
        """Test criminal allegation with named person results in critical risk tier."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Jane Smith",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_4_{uuid4().hex[:8]}",
            claim_type="criminal_allegation",
            entity_id=entity.id,
            claim_value="Charged with assault",
            confidence=0.60,
            contradiction_count=0,
            corroboration_count=1,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert tier == "critical"

    def test_low_confidence_claim_high_risk(self, db_session):
        """Test low confidence claim results in high/critical risk tier."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Bob Johnson",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_5_{uuid4().hex[:8]}",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            confidence=0.30,  # Low confidence
            contradiction_count=0,
            corroboration_count=1,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        tier = calculate_claim_review_priority_tier(claim.id, db_session)
        assert tier in ["high", "critical"]


class TestReviewRequirements:
    """Test review requirements per review-priority tier."""

    def test_critical_requires_review_and_evidence(self):
        """Test critical tier requires review and evidence."""
        requirements = get_review_requirements("critical")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is True
        assert requirements["auto_approve"] is False

    def test_high_requires_review_and_evidence(self):
        """Test high tier requires review and evidence."""
        requirements = get_review_requirements("high")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is True
        assert requirements["auto_approve"] is False

    def test_medium_requires_review_only(self):
        """Test medium tier requires review only."""
        requirements = get_review_requirements("medium")
        assert requirements["requires_review"] is True
        assert requirements["requires_evidence"] is False
        assert requirements["auto_approve"] is False

    def test_low_allows_auto_approve(self):
        """Test low tier allows auto-approval."""
        requirements = get_review_requirements("low")
        assert requirements["requires_review"] is False
        assert requirements["requires_evidence"] is False
        assert requirements["auto_approve"] is True


class TestAutoApproval:
    """Test auto-approval logic."""

    def test_low_risk_can_auto_approve(self, db_session):
        """Test low risk claims can be auto-approved."""
        entity = CanonicalEntity(
            entity_type="statute",
            canonical_name="Test Statute",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_6_{uuid4().hex[:8]}",
            claim_type="statute_text",
            entity_id=entity.id,
            claim_value="Text",
            confidence=0.95,
            contradiction_count=0,
            corroboration_count=5,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        can_approve = can_auto_approve(claim.id, db_session)
        assert can_approve is True

    def test_high_risk_cannot_auto_approve(self, db_session):
        """Test high risk claims cannot be auto-approved."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Test Person",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key=f"test_claim_7_{uuid4().hex[:8]}",
            claim_type="criminal_allegation",
            entity_id=entity.id,
            claim_value="Allegation",
            confidence=0.60,
            contradiction_count=0,
            corroboration_count=1,
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        can_approve = can_auto_approve(claim.id, db_session)
        assert can_approve is False


class TestEntityReviewPriorityTier:
    """Test entity-level review-priority tier calculation."""

    def test_entity_risk_max_of_claims(self, db_session):
        """Test entity risk is max of its claims' risks."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Test Entity",
        )
        db_session.add(entity)
        db_session.commit()

        # Low risk claim
        claim1 = MemoryClaim(
            claim_key=f"test_claim_8_{uuid4().hex[:8]}",
            claim_type="alias",
            entity_id=entity.id,
            claim_value="Alias",
            confidence=0.95,
            contradiction_count=0,
            corroboration_count=5,
            is_active=True,
            status="active",
        )
        # Critical risk claim
        claim2 = MemoryClaim(
            claim_key=f"test_claim_9_{uuid4().hex[:8]}",
            claim_type="criminal_allegation",
            entity_id=entity.id,
            claim_value="Allegation",
            confidence=0.60,
            contradiction_count=0,
            corroboration_count=1,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        tier = calculate_entity_review_priority_tier(entity.id, db_session)
        assert tier == "critical"  # Max of low and critical


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
