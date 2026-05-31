"""Tests for public publication gate (Phase 11).

Tests publication gate checks for memory claims.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from uuid import uuid4

from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot, CanonicalEntity
from app.review.publication_gate import (
    PublicationBlockedError,
    assert_memory_claim_publication_ready,
)
from app.db.session import engine


class TestMemoryClaimPublicationGate:
    """Test memory claim publication gate logic."""

    def test_approved_claim_passes_gate(self, db_session):
        """Test that approved claims with evidence pass the gate."""
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
            review_status="approved",
            confidence=0.8,
            contradiction_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        # Add supporting evidence
        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
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

        # Should not raise
        assert_memory_claim_publication_ready(claim, db_session)

    def test_unapproved_claim_fails_gate(self, db_session):
        """Test that unapproved claims fail the gate."""
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
            review_status="pending_review",
            confidence=0.8,
            contradiction_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        with pytest.raises(PublicationBlockedError) as exc_info:
            assert_memory_claim_publication_ready(claim, db_session)

        assert "review_status" in str(exc_info.value).lower()

    def test_claim_without_evidence_fails_gate(self, db_session):
        """Test that claims without evidence fail the gate."""
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
            review_status="approved",
            confidence=0.8,
            contradiction_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        with pytest.raises(PublicationBlockedError) as exc_info:
            assert_memory_claim_publication_ready(claim, db_session)

        assert "evidence" in str(exc_info.value).lower()

    def test_low_confidence_claim_fails_gate(self, db_session):
        """Test that low confidence claims fail the gate."""
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
            review_status="approved",
            confidence=0.5,
            contradiction_count=0,
        )
        db_session.add(claim)
        db_session.commit()

        # Add supporting evidence
        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
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

        with pytest.raises(PublicationBlockedError) as exc_info:
            assert_memory_claim_publication_ready(claim, db_session)

        assert "confidence" in str(exc_info.value).lower()

    def test_claim_with_contradictions_fails_gate(self, db_session):
        """Test that claims with contradictions fail the gate."""
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
            review_status="approved",
            confidence=0.8,
            contradiction_count=2,
        )
        db_session.add(claim)
        db_session.commit()

        # Add supporting evidence
        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
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

        with pytest.raises(PublicationBlockedError) as exc_info:
            assert_memory_claim_publication_ready(claim, db_session)

        assert "contradiction" in str(exc_info.value).lower()


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
