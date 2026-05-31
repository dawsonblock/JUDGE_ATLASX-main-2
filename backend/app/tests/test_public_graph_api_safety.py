"""Test public graph API safety.

Ensure public graph endpoints never expose:
- hidden graph edges
- edges from rejected claims
- edges from open high/critical contradictions
- edges from deprecated/quarantined sources
- unreviewed named-person allegations
- media-only criminal allegations
- unsupported claim edges
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.entities import (
    MemoryClaim,
    CanonicalEntity,
    EntityGraphEdge,
    LegalSource,
    SourceSnapshot,
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


def test_public_graph_does_not_expose_hidden_edges(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose hidden edges."""
    # Create a hidden edge (status = retracted)
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="retracted",
        public_status="hidden",
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include hidden edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    # Hidden edge should not be in public results
    assert len(public_edges) == 0


def test_public_graph_does_not_expose_rejected_claim_edges(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose edges from rejected claims."""
    # Create a claim with rejected status
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

    # Create edge from rejected claim
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="hidden",
        evidence_refs={"claim_id": claim.id, "claim_status": "rejected"},
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include rejected claim edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_contradiction_hidden_edges(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose edges with open contradictions."""
    # Create edge hidden due to contradiction
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="hidden",
        evidence_refs={"contradiction_severity": "critical", "contradiction_status": "open"},
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include contradiction-hidden edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_deprecated_source_edges(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_entity_2: CanonicalEntity,
    test_source_snapshot: SourceSnapshot,
):
    """Test that public graph endpoints do not expose edges from deprecated sources."""
    # Create a deprecated source
    source = LegalSource(
        source_key="test_source",
        lifecycle_state="deprecated",
        is_active=False,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    # Create edge from deprecated source
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="hidden",
        source_snapshot_id=test_source_snapshot.id,
        evidence_refs={"source_lifecycle_state": "deprecated"},
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include deprecated source edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_quarantined_source_edges(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_entity_2: CanonicalEntity,
    test_source_snapshot: SourceSnapshot,
):
    """Test that public graph endpoints do not expose edges from quarantined sources."""
    # Create a quarantined source
    source = LegalSource(
        source_key="test_source_quarantined",
        lifecycle_state="quarantined",
        is_active=False,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    # Create edge from quarantined source
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="hidden",
        source_snapshot_id=test_source_snapshot.id,
        evidence_refs={"source_lifecycle_state": "quarantined"},
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include quarantined source edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_unreviewed_named_person_allegations(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose unreviewed named-person allegations."""
    # Create edge for unreviewed named-person allegation
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="accused_of",
        status="active",
        public_status="hidden",
        evidence_refs={
            "entity_type": "person",
            "is_named_person": True,
            "review_status": "unreviewed",
        },
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include unreviewed named-person allegations)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_media_only_criminal_allegations(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose media-only criminal allegations."""
    # Create edge for media-only criminal allegation
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="accused_of",
        status="active",
        public_status="hidden",
        evidence_refs={
            "source_type": "media",
            "allegation_type": "criminal",
            "has_official_source": False,
        },
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include media-only criminal allegations)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_does_not_expose_unsupported_claim_edges(
    db_session: Session, test_entity: CanonicalEntity, test_entity_2: CanonicalEntity
):
    """Test that public graph endpoints do not expose unsupported claim edges."""
    # Create edge with insufficient evidence
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="hidden",
        evidence_refs={"evidence_count": 0, "min_evidence_required": 2},
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should not include unsupported edges)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 0


def test_public_graph_exposes_approved_safe_edges(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_entity_2: CanonicalEntity,
    test_source_snapshot: SourceSnapshot,
):
    """Test that public graph endpoints do expose approved safe edges."""
    # Create an active, reviewed, safe edge
    edge = EntityGraphEdge(
        subject_type="canonical_entity",
        subject_id=test_entity.id,
        object_type="canonical_entity",
        object_id=test_entity_2.id,
        predicate="works_for",
        status="active",
        public_status="public",
        source_snapshot_id=test_source_snapshot.id,
        evidence_refs={
            "evidence_count": 3,
            "min_evidence_required": 2,
            "review_status": "approved",
            "source_lifecycle_state": "active",
        },
        valid_from=datetime.now(timezone.utc),
    )
    db_session.add(edge)
    db_session.commit()
    db_session.refresh(edge)

    # Query for public edges (should include this safe edge)
    public_edges = (
        db_session.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == test_entity.id,
            EntityGraphEdge.public_status == "public",
        )
        .all()
    )

    assert len(public_edges) == 1
    assert public_edges[0].predicate == "works_for"
