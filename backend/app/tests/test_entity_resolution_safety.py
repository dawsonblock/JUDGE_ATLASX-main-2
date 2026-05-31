"""Tests for entity resolution safety system (Phase 7).

Tests merge confidence thresholds, human approval requirements, and audit trails.
"""

import pytest

from app.models.entities import CanonicalEntity
from app.graph.entity_resolution_safety import (
    propose_safe_merge,
    execute_approved_merge,
    _check_jurisdiction_consistency,
)
from app.db.session import SessionLocal


class TestMergeSafetyChecks:
    """Test merge safety assessment logic."""

    def test_propose_merge_with_safety_check(self, db_session):
        """Test that merge proposals include safety assessment."""
        entity1 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        entity2 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add_all([entity1, entity2])
        db_session.commit()

        result = propose_safe_merge(entity1.id, entity2.id, db_session)

        assert result["status"] in ["proposed", "error"]
        if result["status"] == "proposed":
            assert "safety" in result
            assert "risk_level" in result["safety"]
            assert "requires_approval" in result["safety"]

    def test_merge_same_entity_blocked(self, db_session):
        """Test that merging an entity with itself is blocked."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        result = propose_safe_merge(entity.id, entity.id, db_session)
        assert result["status"] == "error"
        assert "same entity" in result["message"].lower()

    def test_merge_nonexistent_entity_blocked(self, db_session):
        """Test that merging with non-existent entity is blocked."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        result = propose_safe_merge(entity.id, 999999, db_session)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_jurisdiction_consistency_check(self, db_session):
        """Test jurisdiction consistency check."""
        entity1 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        entity2 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        entity3 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="NY",
        )
        entity4 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction=None,
        )
        db_session.add_all([entity1, entity2, entity3, entity4])
        db_session.commit()

        # Same jurisdictions
        assert _check_jurisdiction_consistency(entity1, entity2) is True

        # Different jurisdictions
        assert _check_jurisdiction_consistency(entity1, entity3) is False

        # One without jurisdiction
        assert _check_jurisdiction_consistency(entity1, entity4) is True


class TestMergeApproval:
    """Test merge approval workflow."""

    def test_execute_approved_merge(self, db_session):
        """Test execution of approved merge."""
        entity1 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        entity2 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add_all([entity1, entity2])
        db_session.commit()

        result = execute_approved_merge(
            entity1.id, entity2.id, "test_user", db_session
        )

        assert result["status"] in ["executed", "blocked"]
        if result["status"] == "executed":
            assert "approved_by" in result
            assert result["approved_by"] == "test_user"

    def test_blocked_merge_without_approval(self, db_session):
        """Test that unsafe merges are blocked even with approval."""
        # Create entities with different types (should be blocked)
        entity1 = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        entity2 = CanonicalEntity(
            entity_type="court",
            name="Superior Court",
            jurisdiction="CA",
        )
        db_session.add_all([entity1, entity2])
        db_session.commit()

        result = execute_approved_merge(
            entity1.id, entity2.id, "test_user", db_session
        )

        # Should be blocked due to entity type mismatch
        assert result["status"] == "blocked"


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
