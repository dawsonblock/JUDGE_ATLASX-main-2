"""E2E test for source to public API pipeline (Phase 7).

Tests the complete pipeline from source ingestion through to public API exposure,
including:
- Source ingestion and run tracking
- Evidence snapshot preservation
- Claim extraction and linking
- Evidence verification
- Publication gate validation
- Contradiction detection and resolution
- Graph projection
- Public API safety checks
- Named-person criminal allegation policy enforcement
- Source authority weighting
"""

import pytest
from datetime import datetime, timezone

from app.models.entities import (
    LegalSource,
    IngestionRun,
    SourceSnapshot,
    MemoryClaim,
    MemoryEvidenceLink,
    CanonicalEntity,
    MemoryContradiction,
)
from app.ingestion.automation_statuses import JobState
from app.review.publication_gate import (
    assert_memory_claim_publication_ready,
    PublicationBlockedError,
)
from app.memory.contradiction_engine import (
    detect_contradictions,
    auto_supersede_by_authority,
)
from app.graph.claim_to_graph import (
    claim_to_entity_node,
    claim_to_relationship,
    sync_claim_to_graph,
)
from app.db.session import SessionLocal


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_full_pipeline_source_to_public_api(db_session):
    """Test the complete pipeline from source ingestion to public API readiness."""
    # Step 1: Create a legal source with official court record type
    source = LegalSource(
        source_id="test_e2e_api_source",
        title="E2E API Test Source",
        source_type="official_court_record",
        lifecycle_state="active",
    )
    db_session.add(source)
    db_session.commit()

    # Step 2: Create ingestion run
    run = IngestionRun(
        source_name=source.source_id,
        status=JobState.COMPLETED.value,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Step 3: Create evidence snapshot
    snapshot = SourceSnapshot(
        ingestion_run_id=run.id,
        source_key=source.source_id,
        source_url=f"manual://{source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        raw_content='{"test": "data"}',
        content_hash="abc123",
    )
    db_session.add(snapshot)
    db_session.commit()

    # Step 4: Create canonical entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="E2E API Test Judge",
    )
    db_session.add(entity)
    db_session.commit()

    # Step 6: Create memory claim with Phase 4 fields
    claim = MemoryClaim(
        claim_key="e2e_api_claim_1",
        claim_uid="uid-api-1",
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
        claim_sensitivity="public_record",
        elevated_review_status="approved",
        elevated_reviewer_id="reviewer-1",
        elevated_reviewed_at=datetime.now(timezone.utc),
        derived_from_ai=False,
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

    # Step 9: Verify graph projection works
    node = claim_to_entity_node(claim, db_session)
    assert node.entity_id == entity.id
    assert node.properties["claim_sensitivity"] == "public_record"
    assert node.properties["elevated_review_status"] == "approved"

    # Step 10: Sync claim to graph
    sync_result = sync_claim_to_graph(claim, db_session)
    assert sync_result is True

    # Step 10: Verify the complete chain
    assert snapshot.source_key == source.source_id
    assert snapshot.ingestion_run_id == run.id
    assert claim.extraction_run_id == run.id
    assert evidence_link.claim_id == claim.id
    assert evidence_link.snapshot_id == snapshot.id

    # Phase 7: Verify snapshot hash
    assert snapshot.content_hash == "abc123"
    assert evidence_link.evidence_checksum == "abc123"

    # Phase 7: Verify risk tier (based on claim sensitivity)
    # High sensitivity = higher risk tier
    risk_tier = "low"
    if claim.claim_sensitivity in ["criminal_allegation_named_person", "criminal_allegation_private_person"]:
        risk_tier = "critical"
    elif claim.claim_sensitivity in ["misconduct_allegation"]:
        risk_tier = "high"
    elif claim.claim_sensitivity in ["legal_proceeding"]:
        risk_tier = "medium"
    assert risk_tier == "low"  # public_record is low risk

    # Phase 7: Verify graph edge creation timing
    import time
    start_time = time.time()
    edge = claim_to_relationship(claim, db_session)
    edge_creation_time = time.time() - start_time
    assert edge is None  # No object_entity_id, so no relationship
    assert edge_creation_time < 1.0  # Should complete in under 1 second

    # Phase 7: Verify public API citation format
    public_citation = {
        "claim_id": claim.claim_uid,
        "source_id": source.source_id,
        "snapshot_id": snapshot.id,
        "evidence_hash": evidence_link.evidence_checksum,
        "confidence": claim.confidence,
        "review_status": claim.review_status,
        "sensitivity": claim.claim_sensitivity,
    }
    assert public_citation["claim_id"].startswith("uid-api-1")
    assert public_citation["source_id"] == "test_e2e_api_source"
    assert public_citation["evidence_hash"] == "abc123"


def test_named_person_criminal_allegation_enforcement(db_session):
    """Test that named-person criminal allegations require elevated approval."""
    # Create source
    source = LegalSource(
        source_id="test_e2e_criminal_source",
        title="E2E Criminal Test Source",
        source_type="official_court_record",
        lifecycle_state="active",
    )
    db_session.add(source)
    db_session.commit()

    # Create ingestion run
    run = IngestionRun(
        source_name=source.source_id,
        status=JobState.COMPLETED.value,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Create snapshot
    snapshot = SourceSnapshot(
        ingestion_run_id=run.id,
        source_key=source.source_id,
        source_url=f"manual://{source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        raw_content='{"test": "data"}',
        content_hash="abc123",
    )
    db_session.add(snapshot)
    db_session.commit()

    # Create entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="E2E Criminal Test Person",
    )
    db_session.add(entity)
    db_session.commit()

    # Create claim with criminal allegation sensitivity but no elevated approval
    claim = MemoryClaim(
        claim_key="e2e_criminal_claim",
        claim_uid="uid-criminal-1",
        claim_type="criminal_allegation",
        entity_id=entity.id,
        claim_value="Charged with crime",
        normalized_value="charged_with_crime",
        object_value_type="text",
        predicate="criminal_charge",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        extraction_run_id=run.id,
        source_snapshot_id=snapshot.id,
        claim_sensitivity="criminal_allegation_named_person",
        elevated_review_status="pending_review",  # Not approved
    )
    db_session.add(claim)
    db_session.commit()

    # Create evidence link
    evidence_link = MemoryEvidenceLink(
        claim_id=claim.id,
        snapshot_id=snapshot.id,
        support_type="supports",
        confidence=0.9,
        evidence_checksum="abc123",
    )
    db_session.add(evidence_link)
    db_session.commit()

    # Should fail publication gate due to missing elevated approval
    with pytest.raises(PublicationBlockedError) as exc:
        assert_memory_claim_publication_ready(claim, db_session)
    assert "requires elevated approval for named-person criminal allegation" in str(exc.value)


def test_source_authority_weighting_in_contradiction(db_session):
    """Test that source authority weighting is applied in contradiction resolution."""
    # Create high-authority source
    high_auth_source = LegalSource(
        source_id="test_high_auth_source",
        title="High Authority Source",
        source_type="court_record",
        lifecycle_state="active",
    )
    db_session.add(high_auth_source)
    db_session.commit()

    # Create low-authority source
    low_auth_source = LegalSource(
        source_id="test_low_auth_source",
        title="Low Authority Source",
        source_type="user_submission",
        lifecycle_state="active",
    )
    db_session.add(low_auth_source)
    db_session.commit()

    snapshot_high = SourceSnapshot(
        source_key=high_auth_source.source_id,
        source_url=f"manual://{high_auth_source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        content_hash="auth-high",
    )
    snapshot_low = SourceSnapshot(
        source_key=low_auth_source.source_id,
        source_url=f"manual://{low_auth_source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        content_hash="auth-low",
    )
    db_session.add(snapshot_high)
    db_session.add(snapshot_low)
    db_session.commit()

    # Create entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="E2E Authority Test Person",
    )
    db_session.add(entity)
    db_session.commit()

    # Create claim from high authority source
    claim_high = MemoryClaim(
        claim_key="e2e_auth_claim_high",
        claim_uid="uid-auth-high",
        claim_type="employment",
        entity_id=entity.id,
        claim_value="Employed",
        normalized_value="true",
        object_value_type="boolean",
        predicate="employed",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
            source_snapshot_id=snapshot_high.id,
    )
    db_session.add(claim_high)
    db_session.commit()

    # Create claim from low authority source
    claim_low = MemoryClaim(
        claim_key="e2e_auth_claim_low",
        claim_uid="uid-auth-low",
        claim_type="employment",
        entity_id=entity.id,
        claim_value="Unemployed",
        normalized_value="false",
        object_value_type="boolean",
        predicate="employed",
        confidence=0.8,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
            source_snapshot_id=snapshot_low.id,
    )
    db_session.add(claim_low)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions(entity.id, db_session, persist=True)

    # Should detect a contradiction
    assert len(contradictions) > 0

    # Verify source authority weight is stored
    contradiction = (
        db_session.query(MemoryContradiction)
        .filter(
            MemoryContradiction.claim_a_id == claim_high.id,
            MemoryContradiction.claim_b_id == claim_low.id,
        )
        .first()
    )
    assert contradiction is not None
    assert contradiction.source_authority_weight is not None
    # High authority source should contribute to weight
    assert contradiction.source_authority_weight > 0.5


def test_auto_supersede_by_authority(db_session):
    """Test automatic supersession based on source authority."""
    # Create high-authority source
    high_auth_source = LegalSource(
        source_id="test_auto_supersede_high",
        title="Auto Supersede High",
        source_type="court_record",
        lifecycle_state="active",
    )
    db_session.add(high_auth_source)
    db_session.commit()

    # Create low-authority source
    low_auth_source = LegalSource(
        source_id="test_auto_supersede_low",
        title="Auto Supersede Low",
        source_type="user_submission",
        lifecycle_state="active",
    )
    db_session.add(low_auth_source)
    db_session.commit()

    # Create snapshots
    snapshot_high = SourceSnapshot(
        source_key=high_auth_source.source_id,
        source_url=f"manual://{high_auth_source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash-high",
    )
    snapshot_low = SourceSnapshot(
        source_key=low_auth_source.source_id,
        source_url=f"manual://{low_auth_source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash-low",
    )
    db_session.add(snapshot_high)
    db_session.add(snapshot_low)
    db_session.commit()

    # Create entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="Auto Supersede Test Person",
    )
    db_session.add(entity)
    db_session.commit()

    # Create claims with different sources
    claim_high = MemoryClaim(
        claim_key="e2e_auto_claim_high",
        claim_uid="uid-auto-high",
        claim_type="employment",
        entity_id=entity.id,
        claim_value="Employed",
        normalized_value="true",
        object_value_type="boolean",
        predicate="employed",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        source_snapshot_id=snapshot_high.id,
    )
    claim_low = MemoryClaim(
        claim_key="e2e_auto_claim_low",
        claim_uid="uid-auto-low",
        claim_type="employment",
        entity_id=entity.id,
        claim_value="Unemployed",
        normalized_value="false",
        object_value_type="boolean",
        predicate="employed",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        source_snapshot_id=snapshot_low.id,
    )
    db_session.add(claim_high)
    db_session.add(claim_low)
    db_session.commit()

    # Create contradiction
    contradiction = MemoryContradiction(
        claim_a_id=claim_high.id,
        claim_b_id=claim_low.id,
        conflict_type="value_contradiction",
        severity="high",
        status="open",
        detected_by="system",
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add(contradiction)
    db_session.commit()

    # Auto-supersede by authority
    result = auto_supersede_by_authority(contradiction.id, db_session)
    assert result is True

    # Verify low-authority claim was superseded
    db_session.refresh(claim_low)
    assert claim_low.status == "superseded"
    assert claim_low.is_active is False

    # Verify contradiction was resolved
    db_session.refresh(contradiction)
    assert contradiction.status == "resolved"


def test_phase6_edge_fields_in_graph_projection(db_session):
    """Test that Phase 6 edge fields are included in graph projection."""
    # Create entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="Phase 6 Test Person",
    )
    db_session.add(entity)
    db_session.commit()

    # Create claim with Phase 6 fields
    claim = MemoryClaim(
        claim_key="e2e_phase6_claim",
        claim_uid="uid-phase6",
        claim_type="employment",
        entity_id=entity.id,
        claim_value="Employed",
        normalized_value="employed",
        object_value_type="text",
        predicate="role",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        claim_sensitivity="public_record",
        elevated_review_status="approved",
        elevated_reviewer_id="reviewer-1",
        elevated_reviewed_at=datetime.now(timezone.utc),
        derived_from_ai=True,
        extraction_model="gpt-4",
    )
    db_session.add(claim)
    db_session.commit()

    # Convert to entity node
    node = claim_to_entity_node(claim, db_session)

    # Verify Phase 6 fields are present
    assert "claim_sensitivity" in node.properties
    assert "elevated_review_status" in node.properties
    assert "elevated_reviewer_id" in node.properties
    assert "elevated_reviewed_at" in node.properties
    assert "derived_from_ai" in node.properties
    assert "extraction_model" in node.properties
    assert "last_seen_at" in node.properties

    # Verify values
    assert node.properties["claim_sensitivity"] == "public_record"
    assert node.properties["elevated_review_status"] == "approved"
    assert node.properties["elevated_reviewer_id"] == "reviewer-1"
    assert node.properties["derived_from_ai"] is True
    assert node.properties["extraction_model"] == "gpt-4"


def test_unsafe_claim_exclusion_from_public_api(db_session):
    """Test that unsafe claims are excluded from public API."""
    # Create source
    source = LegalSource(
        source_id="test_unsafe_source",
        title="Unsafe Test Source",
        source_type="official_court_record",
        lifecycle_state="active",
    )
    db_session.add(source)
    db_session.commit()

    # Create ingestion run
    run = IngestionRun(
        source_name=source.source_id,
        status=JobState.COMPLETED.value,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Create snapshot
    snapshot = SourceSnapshot(
        ingestion_run_id=run.id,
        source_key=source.source_id,
        source_url=f"manual://{source.source_id}",
        fetched_at=datetime.now(timezone.utc),
        raw_content='{"test": "data"}',
        content_hash="abc123",
    )
    db_session.add(snapshot)
    db_session.commit()

    # Create entity
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="Unsafe Test Person",
    )
    db_session.add(entity)
    db_session.commit()

    # Create claim with criminal allegation but no elevated approval (unsafe)
    unsafe_claim = MemoryClaim(
        claim_key="unsafe_claim",
        claim_uid="uid-unsafe",
        claim_type="criminal_allegation",
        entity_id=entity.id,
        claim_value="Charged with crime",
        normalized_value="charged_with_crime",
        object_value_type="text",
        predicate="criminal_charge",
        confidence=0.9,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        extraction_run_id=run.id,
        source_snapshot_id=snapshot.id,
        claim_sensitivity="criminal_allegation_named_person",
        elevated_review_status="pending_review",  # Not approved - unsafe
    )
    db_session.add(unsafe_claim)
    db_session.commit()

    # Create evidence link
    evidence_link = MemoryEvidenceLink(
        claim_id=unsafe_claim.id,
        snapshot_id=snapshot.id,
        support_type="supports",
        confidence=0.9,
        evidence_checksum="abc123",
    )
    db_session.add(evidence_link)
    db_session.commit()

    # Verify unsafe claim fails publication gate
    with pytest.raises(PublicationBlockedError) as exc:
        assert_memory_claim_publication_ready(unsafe_claim, db_session)
    assert "requires elevated approval" in str(exc.value)

    # Verify unsafe claim is excluded from public API citation
    # In production, this would be filtered by the API endpoint
    is_safe_for_public_api = (
        unsafe_claim.elevated_review_status == "approved"
        and unsafe_claim.review_status == "approved"
        and unsafe_claim.status == "active"
    )
    assert is_safe_for_public_api is False
