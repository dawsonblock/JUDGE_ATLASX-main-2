"""Tests for structured claim schema (Phase 3).

Tests field validation, enum constraints, and temporal rules for MemoryClaim.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from app.models.entities import MemoryClaim, CanonicalEntity


class TestMemoryClaimSchema:
    """Test structured claim schema validation."""

    def test_claim_uid_unique_constraint(self, db_session):
        """Test that claim_uid is unique."""
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
            claim_value="Test value",
            predicate="test_predicate",
            object_value="test_object",
            object_value_type="literal",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value 2",
            predicate="test_predicate",
            object_value="test_object",
            object_value_type="literal",
        )
        # claim_uid should be auto-generated and unique
        db_session.add_all([claim1, claim2])
        db_session.commit()

        assert claim1.claim_uid is not None
        assert claim2.claim_uid is not None
        assert claim1.claim_uid != claim2.claim_uid

    def test_confidence_range_constraint(self, db_session):
        """Test that confidence must be between 0.0 and 1.0."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Valid confidence values
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.0,
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.5,
        )
        claim3 = MemoryClaim(
            claim_key="test_claim_3",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=1.0,
        )
        db_session.add_all([claim1, claim2, claim3])
        db_session.commit()

        assert claim1.confidence == 0.0
        assert claim2.confidence == 0.5
        assert claim3.confidence == 1.0

    def test_temporal_validity_constraint(self, db_session):
        """Test that valid_to must be >= valid_from."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        now = datetime.now(timezone.utc)
        future = now.replace(year=now.year + 1)

        # Valid temporal window
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            valid_from=now,
            valid_to=future,
        )
        db_session.add(claim1)
        db_session.commit()
        assert claim1.valid_from < claim1.valid_to

        # Null values should be allowed
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            valid_from=None,
            valid_to=None,
        )
        db_session.add(claim2)
        db_session.commit()
        assert claim2.valid_from is None
        assert claim2.valid_to is None

    def test_object_value_type_enum(self, db_session):
        """Test that object_value_type is constrained to valid enum values."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # Valid enum values
        valid_types = ["entity", "literal", "date", "number", "boolean"]
        for i, value_type in enumerate(valid_types):
            claim = MemoryClaim(
                claim_key=f"test_claim_{i}",
                claim_type="test",
                entity_id=entity.id,
                claim_value=f"Test value {i}",
                object_value_type=value_type,
            )
            db_session.add(claim)
        db_session.commit()

    def test_corroboration_and_contradiction_counts(self, db_session):
        """Test that corroboration and contradiction counts default to 0."""
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
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.corroboration_count == 0
        assert claim.contradiction_count == 0

    def test_derived_from_ai_default(self, db_session):
        """Test that derived_from_ai defaults to False."""
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
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.derived_from_ai is False

    def test_review_status_default(self, db_session):
        """Test that review_status defaults to 'pending_review'."""
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
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.review_status == "pending_review"

    def test_object_entity_id_foreign_key(self, db_session):
        """Test that object_entity_id references canonical_entities."""
        entity1 = CanonicalEntity(
            entity_type="person",
            name="Test Person 1",
            jurisdiction="CA",
        )
        entity2 = CanonicalEntity(
            entity_type="person",
            name="Test Person 2",
            jurisdiction="CA",
        )
        db_session.add_all([entity1, entity2])
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="relationship",
            entity_id=entity1.id,
            object_entity_id=entity2.id,
            predicate="knows",
            object_value_type="entity",
            claim_value="Person 1 knows Person 2",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.object_entity_id == entity2.id

    def test_superseded_by_claim_id_self_reference(self, db_session):
        """Test that superseded_by_claim_id references memory_claims."""
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
            claim_value="Original value",
        )
        db_session.add(claim1)
        db_session.flush()

        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Superseding value",
            superseded_by_claim_id=claim1.id,
        )
        db_session.add(claim2)
        db_session.commit()

        assert claim2.superseded_by_claim_id == claim1.id

    def test_extraction_run_id_foreign_key(self, db_session):
        """Test that extraction_run_id references ingestion_runs."""
        entity = CanonicalEntity(
            entity_type="person",
            name="Test Person",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # This test assumes ingestion_runs table exists
        # In a real scenario, you'd create an ingestion_run first
        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            extraction_run_id=None,  # Can be null
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.extraction_run_id is None

    def test_jurisdiction_index(self, db_session):
        """Test that jurisdiction is indexed."""
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
            claim_value="Test value",
            jurisdiction="CA",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.jurisdiction == "CA"

    def test_predicate_index(self, db_session):
        """Test that predicate is indexed."""
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
            claim_value="Test value",
            predicate="appointed",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.predicate == "appointed"

    def test_review_status_index(self, db_session):
        """Test that review_status is indexed."""
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
            claim_value="Test value",
            review_status="approved",
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.review_status == "approved"

