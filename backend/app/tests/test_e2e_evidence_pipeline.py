"""E2E test for evidence pipeline (Phase 8).

Tests the complete evidence pipeline from source ingestion through
to claim publication, including:
- Source ingestion and run tracking
- Evidence snapshot preservation
- Claim extraction and linking
- Evidence verification
- Publication gate validation
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.entities import (
    LegalSource,
    IngestionRun,
    SourceSnapshot,
    ReviewItem,
    MemoryClaim,
    MemoryEvidenceLink,
    CanonicalEntity,
    MemoryContradiction,
    EntityGraphEdge,
)
from app.ingestion.automation_statuses import JobState
from app.review.publication_gate import (
    assert_memory_claim_publication_ready,
    PublicationBlockedError,
)
from app.memory.contradiction_engine import detect_contradictions
from app.db.session import SessionLocal


class TestEvidencePipelineE2E:
    """End-to-end test of the evidence pipeline."""

    def test_complete_evidence_pipeline(self, db_session):
        """Test the full evidence pipeline from ingestion to publication."""
        # Step 1: Create a legal source
        source = LegalSource(
            source_id="test_e2e_source",
            source_name="E2E Test Source",
            lifecycle_state="active",
        )
        db_session.add(source)
        db_session.commit()

        # Step 2: Create ingestion run
        run = IngestionRun(
            source_id=source.id,
            status=JobState.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Step 3: Create evidence snapshot
        snapshot = SourceSnapshot(
            run_id=run.id,
            snapshot_id="e2e_snapshot_1",
            source_id=source.id,
            snapshot_timestamp=datetime.now(timezone.utc),
            raw_content=b'{"test": "data"}',
            content_hash="abc123",
            preserved=True,
        )
        db_session.add(snapshot)
        db_session.commit()

        # Step 4: Create review item linked to snapshot
        review_item = ReviewItem(
            source_snapshot_id=snapshot.id,
            status="approved",
            item_type="case",
        )
        db_session.add(review_item)
        db_session.commit()

        # Step 5: Create canonical entity
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="E2E Test Judge",
        )
        db_session.add(entity)
        db_session.commit()

        # Step 6: Create memory claim
        claim = MemoryClaim(
            claim_key="e2e_claim_1",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.85,
            contradiction_count=0,
            review_status="approved",
            status="active",
            is_active=True,
            extraction_run_id=run.id,
        )
        db_session.add(claim)
        db_session.commit()

        # Step 7: Link claim to evidence
        evidence_link = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            support_type="supports",
            confidence=0.85,
            evidence_checksum="abc123",
        )
        db_session.add(evidence_link)
        db_session.commit()

        # Step 8: Verify publication gate passes
        assert_memory_claim_publication_ready(claim, db_session)

        # Step 9: Verify the complete chain
        assert snapshot.source_id == source.id
        assert snapshot.run_id == run.id
        assert review_item.source_snapshot_id == snapshot.id
        assert claim.extraction_run_id == run.id
        assert evidence_link.claim_id == claim.id
        assert evidence_link.snapshot_id == snapshot.id

    def test_evidence_pipeline_with_missing_snapshot(self, db_session):
        """Test that publication gate fails when evidence snapshot is missing."""
        source = LegalSource(
            source_id="test_e2e_source_2",
            source_name="E2E Test Source 2",
            lifecycle_state="active",
        )
        db_session.add(source)
        db_session.commit()

        run = IngestionRun(
            source_id=source.id,
            status=JobState.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="E2E Test Judge 2",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="e2e_claim_2",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.85,
            contradiction_count=0,
            review_status="approved",
            status="active",
            is_active=True,
            extraction_run_id=run.id,
        )
        db_session.add(claim)
        db_session.commit()

        # No evidence link - should fail publication gate
        with pytest.raises(PublicationBlockedError) as exc:
            assert_memory_claim_publication_ready(claim, db_session)
        assert "no supporting evidence links" in str(exc.value)

    def test_evidence_pipeline_with_deprecated_source(self, db_session):
        """Test that publication gate fails when source is deprecated."""
        source = LegalSource(
            source_id="test_e2e_source_3",
            source_name="E2E Test Source 3",
            lifecycle_state="deprecated",
        )
        db_session.add(source)
        db_session.commit()

        run = IngestionRun(
            source_id=source.id,
            status=JobState.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        snapshot = SourceSnapshot(
            run_id=run.id,
            snapshot_id="e2e_snapshot_3",
            source_id=source.id,
            snapshot_timestamp=datetime.now(timezone.utc),
            raw_content=b'{"test": "data"}',
            content_hash="abc123",
            preserved=True,
        )
        db_session.add(snapshot)
        db_session.commit()

        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="E2E Test Judge 3",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="e2e_claim_3",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.85,
            contradiction_count=0,
            review_status="approved",
            status="active",
            is_active=True,
            extraction_run_id=run.id,
        )
        db_session.add(claim)
        db_session.commit()

        evidence_link = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            support_type="supports",
            confidence=0.85,
            evidence_checksum="abc123",
        )
        db_session.add(evidence_link)
        db_session.commit()

        # Should fail due to deprecated source
        with pytest.raises(PublicationBlockedError) as exc:
            assert_memory_claim_publication_ready(claim, db_session)
        assert "deprecated" in str(exc.value)

    def test_full_pipeline_with_contradiction_scan_and_graph_edge(
        self, db_session
    ):
        """Test the complete pipeline including contradiction scan and graph edge."""
        # Step 1: Create legal source with official_court_record type
        source = LegalSource(
            source_id="test_e2e_source_full",
            source_name="E2E Full Pipeline Source",
            source_type="official_court_record",
            lifecycle_state="active",
        )
        db_session.add(source)
        db_session.commit()

        # Step 2: Create ingestion run
        run = IngestionRun(
            source_id=source.id,
            status=JobState.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Step 3: Create evidence snapshot
        snapshot = SourceSnapshot(
            run_id=run.id,
            snapshot_id="e2e_snapshot_full",
            source_id=source.id,
            snapshot_timestamp=datetime.now(timezone.utc),
            raw_content=b'{"test": "data"}',
            content_hash="abc123",
            preserved=True,
        )
        db_session.add(snapshot)
        db_session.commit()

        # Step 4: Create two canonical entities for relationship
        entity1 = CanonicalEntity(
            entity_type="person",
            canonical_name="E2E Test Judge Full",
        )
        entity2 = CanonicalEntity(
            entity_type="court",
            canonical_name="E2E Test Court Full",
        )
        db_session.add(entity1)
        db_session.add(entity2)
        db_session.commit()

        # Step 5: Create memory claims for both entities
        claim1 = MemoryClaim(
            claim_key="e2e_claim_full_1",
            claim_type="role",
            entity_id=entity1.id,
            source_id=source.id,
            claim_value="Judge",
            normalized_value="Judge",
            object_value_type="text",
            predicate="role",
            confidence=0.85,
            contradiction_count=0,
            review_status="approved",
            status="active",
            is_active=True,
            extraction_run_id=run.id,
        )
        claim2 = MemoryClaim(
            claim_key="e2e_claim_full_2",
            claim_type="location",
            entity_id=entity1.id,
            source_id=source.id,
            claim_value="E2E Test Court Full",
            normalized_value="E2E Test Court Full",
            object_value_type="text",
            predicate="location",
            confidence=0.85,
            contradiction_count=0,
            review_status="approved",
            status="active",
            is_active=True,
            extraction_run_id=run.id,
        )
        db_session.add(claim1)
        db_session.add(claim2)
        db_session.commit()

        # Step 6: Link claims to evidence
        evidence_link1 = MemoryEvidenceLink(
            claim_id=claim1.id,
            snapshot_id=snapshot.id,
            support_type="supports",
            confidence=0.85,
            evidence_checksum="abc123",
        )
        evidence_link2 = MemoryEvidenceLink(
            claim_id=claim2.id,
            snapshot_id=snapshot.id,
            support_type="supports",
            confidence=0.85,
            evidence_checksum="abc123",
        )
        db_session.add(evidence_link1)
        db_session.add(evidence_link2)
        db_session.commit()

        # Step 7: Run contradiction scan
        contradictions = detect_contradictions(entity1.id, db_session, persist=True)
        # Should have no contradictions since claims are about different predicates
        assert len(contradictions) == 0

        # Step 8: Verify publication gate passes for both claims
        assert_memory_claim_publication_ready(claim1, db_session)
        assert_memory_claim_publication_ready(claim2, db_session)

        # Step 9: Create graph edge between entities
        graph_edge = EntityGraphEdge(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            edge_type="appointed_at",
            confidence=0.85,
            support_claim_id=claim2.id,
        )
        db_session.add(graph_edge)
        db_session.commit()

        # Step 10: Verify the complete chain
        assert snapshot.source_id == source.id
        assert snapshot.run_id == run.id
        assert claim1.source_id == source.id
        assert claim2.source_id == source.id
        assert evidence_link1.claim_id == claim1.id
        assert evidence_link2.claim_id == claim2.id
        assert graph_edge.source_entity_id == entity1.id
        assert graph_edge.target_entity_id == entity2.id
        assert graph_edge.support_claim_id == claim2.id


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
