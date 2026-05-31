"""Tests for durable contradiction system (Phase 3).

Tests contradiction persistence, duplicate prevention, and reviewer resolution.
"""

import pytest

from app.models.entities import (
    MemoryClaim,
    CanonicalEntity,
    MemoryContradiction,
)
from app.memory.contradiction_engine import (
    detect_contradictions,
    get_open_contradictions_by_claim,
    get_open_contradictions_by_entity,
    resolve_contradiction_record,
    update_contradiction_counts,
)
from app.db.session import SessionLocal


class TestContradictionPersistence:
    """Test contradiction persistence to database."""

    def test_detect_and_persist_contradiction(self, db_session):
        """Test that detected contradictions are persisted to database."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        db_session.add(entity)
        db_session.commit()

        # Create two conflicting claims
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.80,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            normalized_value="Prosecutor",
            object_value_type="text",
            predicate="role",
            confidence=0.75,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        # Detect and persist contradictions
        contradictions = detect_contradictions(entity.id, db_session, persist=True)

        # Check that contradiction was persisted
        persisted = (
            db_session.query(MemoryContradiction)
            .filter(
                MemoryContradiction.claim_a_id == claim1.id,
                MemoryContradiction.claim_b_id == claim2.id,
            )
            .first()
        )
        assert persisted is not None
        assert persisted.status == "open"
        assert persisted.detected_by == "system"

        # Check that contradiction counts were incremented
        db_session.refresh(claim1)
        db_session.refresh(claim2)
        assert claim1.contradiction_count > 0
        assert claim2.contradiction_count > 0

    def test_duplicate_contradiction_prevention(self, db_session):
        """Test that duplicate contradictions are prevented."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Jane Smith",
        )
        db_session.add(entity)
        db_session.commit()

        claim1 = MemoryClaim(
            claim_key="test_claim_3",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.80,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_4",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            normalized_value="Prosecutor",
            object_value_type="text",
            predicate="role",
            confidence=0.75,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        # Detect contradictions twice
        detect_contradictions(entity.id, db_session, persist=True)
        detect_contradictions(entity.id, db_session, persist=True)

        # Check that only one contradiction exists
        contradictions = (
            db_session.query(MemoryContradiction)
            .filter(
                MemoryContradiction.claim_a_id == claim1.id,
                MemoryContradiction.claim_b_id == claim2.id,
            )
            .all()
        )
        assert len(contradictions) == 1


class TestOpenContradictionLookup:
    """Test open contradiction lookup functions."""

    def test_get_open_contradictions_by_claim(self, db_session):
        """Test retrieving open contradictions for a specific claim."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Bob Johnson",
        )
        db_session.add(entity)
        db_session.commit()

        claim1 = MemoryClaim(
            claim_key="test_claim_5",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.80,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_6",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            normalized_value="Prosecutor",
            object_value_type="text",
            predicate="role",
            confidence=0.75,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        # Create and persist a contradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim1.id,
            claim_b_id=claim2.id,
            conflict_type="value_conflict",
            severity="medium",
            status="open",
            detected_by="system",
        )
        db_session.add(contradiction)
        db_session.commit()

        # Retrieve open contradictions for claim1
        open_contradictions = get_open_contradictions_by_claim(claim1.id, db_session)
        assert len(open_contradictions) == 1
        assert open_contradictions[0].status == "open"

    def test_get_open_contradictions_by_entity(self, db_session):
        """Test retrieving open contradictions for an entity."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Alice Williams",
        )
        db_session.add(entity)
        db_session.commit()

        claim1 = MemoryClaim(
            claim_key="test_claim_7",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.80,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_8",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            normalized_value="Prosecutor",
            object_value_type="text",
            predicate="role",
            confidence=0.75,
            contradiction_count=0,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        # Create and persist a contradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim1.id,
            claim_b_id=claim2.id,
            conflict_type="value_conflict",
            severity="medium",
            status="open",
            detected_by="system",
        )
        db_session.add(contradiction)
        db_session.commit()

        # Retrieve open contradictions for the entity
        open_contradictions = get_open_contradictions_by_entity(entity.id, db_session)
        assert len(open_contradictions) == 1


class TestReviewerResolution:
    """Test reviewer resolution of contradictions."""

    def test_resolve_contradiction_record(self, db_session):
        """Test resolving a contradiction record with reviewer action."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="Charlie Brown",
        )
        db_session.add(entity)
        db_session.commit()

        claim1 = MemoryClaim(
            claim_key="test_claim_9",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.80,
            contradiction_count=1,
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_10",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Prosecutor",
            normalized_value="Prosecutor",
            object_value_type="text",
            predicate="role",
            confidence=0.75,
            contradiction_count=1,
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        # Create and persist a contradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim1.id,
            claim_b_id=claim2.id,
            conflict_type="value_conflict",
            severity="medium",
            status="open",
            detected_by="system",
        )
        db_session.add(contradiction)
        db_session.commit()

        # Resolve the contradiction
        success = resolve_contradiction_record(
            contradiction.id,
            status="resolved",
            reviewer_id=1,
            resolution_note="Verified as false positive",
            db=db_session,
        )
        assert success is True

        # Check that contradiction was resolved
        db_session.refresh(contradiction)
        assert contradiction.status == "resolved"
        assert contradiction.reviewer_id == 1
        assert contradiction.resolution_note == "Verified as false positive"
        assert contradiction.resolved_at is not None

    def test_resolve_nonexistent_contradiction_fails(self, db_session):
        """Test that resolving nonexistent contradiction fails."""
        success = resolve_contradiction_record(
            99999,
            status="resolved",
            reviewer_id=1,
            resolution_note="Test",
            db=db_session,
        )
        assert success is False


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
