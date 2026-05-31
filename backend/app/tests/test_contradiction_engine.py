"""Tests for contradiction engine (Phase 5).

Tests contradiction detection and resolution logic.
"""

import pytest
from datetime import datetime, timezone

from app.models.entities import MemoryClaim, CanonicalEntity
from app.memory.contradiction_engine import (
    detect_contradictions,
    update_contradiction_counts,
    resolve_contradiction,
)
from app.db.session import engine
from sqlalchemy.orm import Session


class TestContradictionDetection:
    """Test contradiction detection logic."""

    def test_detect_boolean_contradiction(self, db_session):
        """Test detection of boolean value contradictions."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Create contradictory boolean claims
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="is_active",
            object_value_type="boolean",
            normalized_value="true",
            claim_value="Person is active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            predicate="is_active",
            object_value_type="boolean",
            normalized_value="false",
            claim_value="Person is not active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        contradictions = detect_contradictions(entity.id, db_session)
        assert len(contradictions) == 1
        assert contradictions[0]["type"] == "value_contradiction"
        assert contradictions[0]["severity"] == "high"

    def test_detect_numeric_contradiction(self, db_session):
        """Test detection of numeric value contradictions."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Create contradictory numeric claims (10% difference threshold)
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="age",
            object_value_type="number",
            normalized_value="50",
            claim_value="Person is 50 years old",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            predicate="age",
            object_value_type="number",
            normalized_value="60",
            claim_value="Person is 60 years old",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        contradictions = detect_contradictions(entity.id, db_session)
        assert len(contradictions) == 1
        assert contradictions[0]["type"] == "value_contradiction"
        assert contradictions[0]["severity"] == "medium"

    def test_detect_temporal_contradiction(self, db_session):
        """Test detection of temporal validity contradictions."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        now = datetime.now(timezone.utc)

        # Create claims with same validity start but different values
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
            valid_from=now,
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="Los Angeles",
            claim_value="Person is in Los Angeles",
            valid_from=now,
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        contradictions = detect_contradictions(entity.id, db_session)
        assert len(contradictions) == 1
        assert contradictions[0]["type"] == "temporal_contradiction"

    def test_no_contradiction_for_same_values(self, db_session):
        """Test that identical values don't trigger contradictions."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        contradictions = detect_contradictions(entity.id, db_session)
        assert len(contradictions) == 0


class TestContradictionResolution:
    """Test contradiction resolution workflow."""

    def test_resolve_contradiction_by_supersede(self, db_session):
        """Test resolving contradiction by superseding a claim."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        assert resolve_contradiction(claim.id, "supersede", db_session) is True

        db_session.refresh(claim)
        assert claim.status == "superseded"
        assert claim.is_active is False
        assert claim.invalidation_reason == "Contradiction resolved by supersession"

    def test_resolve_contradiction_by_invalidate(self, db_session):
        """Test resolving contradiction by invalidating a claim."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
            is_active=True,
            status="active",
        )
        db_session.add(claim)
        db_session.commit()

        assert resolve_contradiction(claim.id, "invalidate", db_session) is True

        db_session.refresh(claim)
        assert claim.status == "invalid"
        assert claim.is_active is False
        assert claim.invalidation_reason == "Contradiction resolved by invalidation"

    def test_resolve_contradiction_invalid_type(self, db_session):
        """Test that invalid resolution type fails."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="location",
            normalized_value="New York",
            claim_value="Person is in New York",
        )
        db_session.add(claim)
        db_session.commit()

        assert resolve_contradiction(claim.id, "invalid_type", db_session) is False


class TestContradictionCountUpdate:
    """Test contradiction count updates."""

    def test_update_contradiction_counts(self, db_session):
        """Test that contradiction counts are updated correctly."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Create contradictory claims
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            predicate="is_active",
            object_value_type="boolean",
            normalized_value="true",
            claim_value="Person is active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            predicate="is_active",
            object_value_type="boolean",
            normalized_value="false",
            claim_value="Person is not active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        entities_with_contradictions = update_contradiction_counts(db_session)
        assert entities_with_contradictions == 1

        db_session.refresh(claim1)
        db_session.refresh(claim2)
        assert claim1.contradiction_count == 1
        assert claim2.contradiction_count == 1


@pytest.fixture
def db_session():
    """Create an isolated database session for testing."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
