"""Tests for claim to graph projection (Phase 6)."""
import pytest
from datetime import datetime, timezone

from app.models.entities import MemoryClaim, CanonicalEntity, MemoryContradiction
from app.graph.claim_to_graph import (
    claim_to_entity_node,
    claim_to_relationship,
    batch_claims_to_graph,
    sync_claim_to_graph,
)
from app.db.session import SessionLocal


def test_claim_to_entity_node_includes_phase6_fields():
    """Test that entity node includes Phase 6 edge fields."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create claim with Phase 6 fields
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
            claim_sensitivity="public_record",
            elevated_review_status="approved",
            elevated_reviewer_id="reviewer-1",
            elevated_reviewed_at=datetime.now(timezone.utc),
            derived_from_ai=True,
            extraction_model="gpt-4",
        )
        db.add(claim)
        db.commit()

        # Convert to entity node
        node = claim_to_entity_node(claim, db)

        # Verify Phase 6 fields are included
        assert node.properties["claim_sensitivity"] == "public_record"
        assert node.properties["elevated_review_status"] == "approved"
        assert node.properties["elevated_reviewer_id"] == "reviewer-1"
        assert node.properties["elevated_reviewed_at"] is not None
        assert node.properties["derived_from_ai"] is True
        assert node.properties["extraction_model"] == "gpt-4"

    finally:
        db.close()


def test_claim_to_relationship_includes_phase6_fields():
    """Test that relationship edge includes Phase 6 edge fields."""
    db = SessionLocal()

    try:
        # Create entities
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        # Create claim with object entity
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
            claim_sensitivity="public_record",
            elevated_review_status="approved",
            elevated_reviewer_id="reviewer-1",
            elevated_reviewed_at=datetime.now(timezone.utc),
            derived_from_ai=False,
            extraction_model=None,
        )
        db.add(claim)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Verify relationship was created
        assert edge is not None
        assert edge.source_entity_id == entity1.id
        assert edge.target_entity_id == entity2.id

        # Verify Phase 6 fields are included
        assert edge.properties["claim_sensitivity"] == "public_record"
        assert edge.properties["elevated_review_status"] == "approved"
        assert edge.properties["elevated_reviewer_id"] == "reviewer-1"
        assert edge.properties["elevated_reviewed_at"] is not None
        assert edge.properties["derived_from_ai"] is False

    finally:
        db.close()


def test_claim_to_relationship_returns_none_for_literal_values():
    """Test that claim_to_relationship returns None for non-entity claims."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create claim without object entity (literal value)
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
        )
        db.add(claim)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Should return None for literal claims
        assert edge is None

    finally:
        db.close()


def test_batch_claims_to_graph():
    """Test batch processing of claims to graph."""
    db = SessionLocal()

    try:
        # Create entities
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        # Create multiple claims
        claim1 = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
        )
        claim2 = MemoryClaim(
            claim_key="test-claim-2",
            claim_uid="uid-2",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.8,
            object_value_type="entity",
            predicate="employed_at",
        )
        db.add(claim1)
        db.add(claim2)
        db.commit()

        # Batch process claims
        stats = batch_claims_to_graph([claim1, claim2], db, include_relationships=True)

        # Verify statistics
        assert stats["entities_created"] == 2
        assert stats["relationships_created"] == 1
        assert len(stats["errors"]) == 0

    finally:
        db.close()


def test_sync_claim_to_graph():
    """Test syncing a single claim to graph."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create claim
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
        )
        db.add(claim)
        db.commit()

        # Sync claim to graph
        result = sync_claim_to_graph(claim, db)

        # Verify sync succeeded
        assert result is True

    finally:
        db.close()


def test_claim_to_entity_node_raises_error_for_missing_entity():
    """Test that claim_to_entity_node raises ValueError for missing entity."""
    db = SessionLocal()

    try:
        # Create claim with non-existent entity
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=99999,  # Non-existent entity
            claim_value="Employed",
            normalized_value="employed",
            confidence=0.9,
            object_value_type="literal",
        )

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            claim_to_entity_node(claim, db)

        assert "Entity 99999 not found" in str(exc_info.value)

    finally:
        db.close()


def test_claim_to_relationship_raises_error_for_missing_entity():
    """Test that claim_to_relationship raises ValueError for missing entity."""
    db = SessionLocal()

    try:
        # Create entity
        entity = CanonicalEntity(name="Test Entity", entity_type="person")
        db.add(entity)
        db.commit()

        # Create claim with non-existent object entity
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity.id,
            object_entity_id=99999,  # Non-existent entity
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
        )

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            claim_to_relationship(claim, db)

        assert "Target entity 99999 not found" in str(exc_info.value)

    finally:
        db.close()


def test_claim_to_relationship_hides_disputed_status_edges():
    """Test that claim_to_relationship hides edges for disputed claims."""
    db = SessionLocal()

    try:
        # Create entities
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        # Create claim with disputed status
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
            status="disputed",  # Disputed status
        )
        db.add(claim)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Should return None for disputed claims
        assert edge is None

    finally:
        db.close()


def test_claim_to_relationship_hides_rejected_status_edges():
    """Test that claim_to_relationship hides edges for rejected claims."""
    db = SessionLocal()

    try:
        # Create entities
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        # Create claim with rejected status
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
            status="rejected",  # Rejected status
        )
        db.add(claim)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Should return None for rejected claims
        assert edge is None

    finally:
        db.close()


def test_claim_to_relationship_hides_superseded_status_edges():
    """Test that claim_to_relationship hides edges for superseded claims."""
    db = SessionLocal()

    try:
        # Create entities
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        # Create claim with superseded status
        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
            status="superseded",  # Superseded status
        )
        db.add(claim)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Should return None for superseded claims
        assert edge is None

    finally:
        db.close()


def test_claim_to_relationship_hides_critical_contradiction_edges():
    """Test that claim_to_relationship hides edges with open critical contradictions."""
    db = SessionLocal()

    try:
        # Create entities and claim
        entity1 = CanonicalEntity(name="Person A", entity_type="person")
        entity2 = CanonicalEntity(name="Company B", entity_type="organization")
        db.add(entity1)
        db.add(entity2)
        db.commit()

        claim = MemoryClaim(
            claim_key="test-claim-1",
            claim_uid="uid-1",
            claim_type="employment",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            claim_value="Employed at",
            normalized_value="employed_at",
            confidence=0.9,
            object_value_type="entity",
            predicate="employed_at",
            contradiction_count=1,  # Has contradictions
        )
        db.add(claim)
        db.commit()

        # Create an open critical contradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim.id,
            claim_b_id=claim.id,  # Self-contradiction for test
            conflict_type="value_contradiction",
            severity="critical",
            status="open",  # Open status
        )
        db.add(contradiction)
        db.commit()

        # Convert to relationship edge
        edge = claim_to_relationship(claim, db)

        # Should return None for claims with open critical contradictions
        assert edge is None

    finally:
        db.close()
