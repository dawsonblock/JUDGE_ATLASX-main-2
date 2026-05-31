"""Test source authority supersession logic.

Validate that:
- Official source supersedes lower-authority source
- Same subject + same predicate + newer observed_at triggers supersession
- Older claim marked as superseded with superseded_by_claim_id
- Audit trail preserved (older claims not deleted)
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.entities import (
    MemoryClaim,
    CanonicalEntity,
    LegalSource,
    SourceSnapshot,
)
from app.memory.source_authority import apply_supersession, get_source_authority_weight
from app.db.session import engine


@pytest.fixture
def db_session():
    """Create an isolated database session for testing."""
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, future=True)
    nested = connection.begin_nested()

    @event.listens_for(db, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not getattr(trans._parent, "nested", False):
            nested = connection.begin_nested()

    try:
        yield db
    finally:
        event.remove(db, "after_transaction_end", _restart_savepoint)
        db.close()
        transaction.rollback()
        connection.close()


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
def official_source(db_session: Session):
    """Create an official court source."""
    source = LegalSource(
        source_key="test_court",
        source_type="official_court",
        lifecycle_state="enabled_runnable",
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


@pytest.fixture
def media_source(db_session: Session):
    """Create a media source."""
    source = LegalSource(
        source_key="test_media",
        source_type="recognized_media",
        lifecycle_state="enabled_runnable",
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


@pytest.fixture
def official_snapshot(db_session: Session, official_source: LegalSource):
    """Create a source snapshot from official source."""
    snapshot = SourceSnapshot(
        source_id=official_source.id,
        source_key="test_court",
        content_hash="abc123",
        fetched_at=datetime.now(timezone.utc),
        parser_version="1.0",
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)
    return snapshot


@pytest.fixture
def media_snapshot(db_session: Session, media_source: LegalSource):
    """Create a source snapshot from media source."""
    snapshot = SourceSnapshot(
        source_id=media_source.id,
        source_key="test_media",
        content_hash="def456",
        fetched_at=datetime.now(timezone.utc),
        parser_version="1.0",
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)
    return snapshot


def test_official_source_supersedes_media_source(
    db_session: Session,
    test_entity: CanonicalEntity,
    official_snapshot: SourceSnapshot,
    media_snapshot: SourceSnapshot,
):
    """Test that official source supersedes lower-authority source."""
    # Create older media claim
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=media_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_claim)
    db_session.commit()
    db_session.refresh(old_claim)

    # Create newer official claim
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="acquitted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Apply supersession
    superseded_count = apply_supersession(new_claim, db_session)

    # Verify old claim was superseded
    assert superseded_count == 1
    db_session.refresh(old_claim)
    assert old_claim.status == "superseded"
    assert old_claim.superseded_by_claim_id == new_claim.id
    assert old_claim.superseded_at is not None


def test_same_subject_predicate_newer_date_supersedes(
    db_session: Session,
    test_entity: CanonicalEntity,
    official_snapshot: SourceSnapshot,
):
    """Test that same subject + same predicate + newer date triggers supersession."""
    # Create older claim
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="pending",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_claim)
    db_session.commit()
    db_session.refresh(old_claim)

    # Create newer claim
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Apply supersession
    superseded_count = apply_supersession(new_claim, db_session)

    # Verify old claim was superseded
    assert superseded_count == 1
    db_session.refresh(old_claim)
    assert old_claim.status == "superseded"
    assert old_claim.superseded_by_claim_id == new_claim.id


def test_different_predicate_no_supersession(
    db_session: Session,
    test_entity: CanonicalEntity,
    official_snapshot: SourceSnapshot,
):
    """Test that different predicates do not trigger supersession."""
    # Create old claim with predicate "case_status"
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_claim)
    db_session.commit()
    db_session.refresh(old_claim)

    # Create new claim with different predicate "sentence"
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="sentence",
        normalized_value="5 years",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Apply supersession
    superseded_count = apply_supersession(new_claim, db_session)

    # Verify no supersession occurred
    assert superseded_count == 0
    db_session.refresh(old_claim)
    assert old_claim.status == "active"


def test_older_claim_not_superseded_by_newer(
    db_session: Session,
    test_entity: CanonicalEntity,
    official_snapshot: SourceSnapshot,
):
    """Test that older claim does not supersede newer claim."""
    # Create newer claim
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Create older claim
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="acquitted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_claim)
    db_session.commit()
    db_session.refresh(old_claim)

    # Apply supersession with older claim as "new" claim
    superseded_count = apply_supersession(old_claim, db_session)

    # Verify no supersession occurred (older claim cannot supersede newer)
    assert superseded_count == 0
    db_session.refresh(new_claim)
    assert new_claim.status == "active"


def test_audit_trail_preserved(
    db_session: Session,
    test_entity: CanonicalEntity,
    official_snapshot: SourceSnapshot,
):
    """Test that audit trail is preserved (older claims not deleted)."""
    # Create older claim
    old_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="pending",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_claim)
    db_session.commit()
    old_claim_id = old_claim.id

    # Create newer claim
    new_claim = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=official_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(new_claim)
    db_session.commit()
    db_session.refresh(new_claim)

    # Apply supersession
    apply_supersession(new_claim, db_session)

    # Verify old claim still exists (not deleted)
    old_claim_check = db_session.query(MemoryClaim).filter(
        MemoryClaim.id == old_claim_id
    ).first()
    assert old_claim_check is not None
    assert old_claim_check.status == "superseded"


def test_get_source_authority_weight():
    """Test source authority weight retrieval."""
    assert get_source_authority_weight("official_court") == 1.00
    assert get_source_authority_weight("official_legislation") == 1.00
    assert get_source_authority_weight("recognized_media") == 0.70
    assert get_source_authority_weight("local_media") == 0.55
    assert get_source_authority_weight("user_submission") == 0.30
    assert get_source_authority_weight("unknown") == 0.20
    assert get_source_authority_weight(None) == 0.10
