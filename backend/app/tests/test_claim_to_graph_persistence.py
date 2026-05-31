"""Test claim-to-graph persistence and edge lifecycle.

Tests that claims are correctly persisted to EntityGraphEdge table
and that edge visibility rules work as expected.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.entities import (
    MemoryClaim,
    CanonicalEntity,
    EntityGraphEdge,
    MemoryContradiction,
    SourceSnapshot,
)
from app.graph.claim_to_graph import (
    sync_claim_to_graph,
    remove_claim_from_graph,
)
from app.db.session import get_db


@pytest.fixture
def db_session():
    """Get a database session for testing."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_entity(db_session: Session):
    """Create a test canonical entity."""
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="Test Person",
        normalized_name="test_person",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity


@pytest.fixture
def test_entity_2(db_session: Session):
    """Create a second test canonical entity."""
    entity = CanonicalEntity(
        entity_type="organization",
        canonical_name="Test Organization",
        normalized_name="test_organization",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity


@pytest.fixture
def test_source_snapshot(db_session: Session):
    """Create a test source snapshot."""
    snapshot = SourceSnapshot(
        source_key="test_source",
        content_hash="abc123",
        fetched_at=datetime.now(timezone.utc),
        parser_version="1.0",
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)
    return snapshot


def test_approved_claim_creates_entity_graph_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that an approved claim with object_entity_id creates an EntityGraphEdge."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Sync claim to graph
    success = sync_claim_to_graph(claim, db_session)
    assert success is True

    # Verify edge was created
    edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.object_type == "canonical_entity",
            EntityGraphEdge.object_id == test_entity_2.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges) == 1
    assert edges[0].predicate == "works_for"
    assert edges[0].evidence_refs is not None


def test_rejected_claim_creates_no_public_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that a rejected claim does not create a public graph edge."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="rejected",
        is_active=False,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Sync claim to graph
    success = sync_claim_to_graph(claim, db_session)
    assert success is True

    # Verify no active edge was created
    edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.object_type == "canonical_entity",
            EntityGraphEdge.object_id == test_entity_2.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges) == 0


def test_disputed_claim_hides_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that a disputed claim hides the graph edge."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="disputed",
        is_active=True,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Sync claim to graph
    success = sync_claim_to_graph(claim, db_session)
    assert success is True

    # Verify no active edge was created (edge is hidden)
    edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.object_type == "canonical_entity",
            EntityGraphEdge.object_id == test_entity_2.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges) == 0


def test_superseded_claim_deactivates_old_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that a superseded claim deactivates the old edge."""
    # Create initial claim
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(old_claim)
    db_session.commit()
    db_session.refresh(old_claim)

    # Sync old claim to create edge
    sync_claim_to_graph(old_claim, db_session)

    # Mark old claim as superseded
    old_claim.status = "superseded"
    db_session.commit()

    # Create new claim
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="employed_by",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Sync new claim
    sync_claim_to_graph(new_claim, db_session)

    # Verify old edge is deactivated
    old_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.object_type == "canonical_entity",
            EntityGraphEdge.object_id == test_entity_2.id,
            EntityGraphEdge.predicate == "works_for",
        )
        .all()
    )
    assert len(old_edges) == 1
    assert old_edges[0].status == "retracted"
    assert old_edges[0].valid_until is not None


def test_open_critical_contradiction_hides_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that a claim with open critical contradiction hides the edge."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        contradiction_count=1,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Create open critical contradiction
    contradiction = MemoryContradiction(
        claim_a_id=claim.id,
        claim_b_id=claim.id + 1,  # Placeholder for second claim
        severity="critical",
        status="open",
    )
    db_session.add(contradiction)
    db_session.commit()

    # Sync claim to graph
    success = sync_claim_to_graph(claim, db_session)
    assert success is True

    # Verify no active edge was created (edge is hidden due to contradiction)
    edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.object_type == "canonical_entity",
            EntityGraphEdge.object_id == test_entity_2.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges) == 0


def test_remove_claim_from_graph_deactivates_edge(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that remove_claim_from_graph deactivates edges instead of deleting them."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Sync claim to create edge
    sync_claim_to_graph(claim, db_session)

    # Verify edge was created
    edges_before = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges_before) == 1

    # Remove claim from graph
    success = remove_claim_from_graph(claim, db_session)
    assert success is True

    # Verify edge is deactivated, not deleted
    edges_after = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
        )
        .all()
    )
    assert len(edges_after) == 1
    assert edges_after[0].status == "retracted"
    assert edges_after[0].valid_until is not None


def test_edge_links_back_to_claim_and_evidence(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_entity_2: CanonicalEntity,
    test_source_snapshot: SourceSnapshot,
):
    """Test that graph edges link back to claim and evidence."""
    claim = MemoryClaim(
        entity_id=test_entity.id,
        object_entity_id=test_entity_2.id,
        predicate="works_for",
        claim_type="relationship",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_source_snapshot.id,
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    # Sync claim to graph
    sync_claim_to_graph(claim, db_session)

    # Verify edge links back to claim
    edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.status == "active",
        )
        .all()
    )
    assert len(edges) == 1
    assert edges[0].evidence_refs is not None
    assert edges[0].evidence_refs.get("claim_id") == claim.id
    assert edges[0].source_snapshot_id == test_source_snapshot.id
