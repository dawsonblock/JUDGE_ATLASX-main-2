from __future__ import annotations

from datetime import datetime, timezone

from app.models.entities import RelationshipEvidence, SourceSnapshot
from app.policies.publication_policy import (
    can_publish_entity,
    can_show_public_entity,
)


def _snapshot(db_session, *, content_hash: str | None = "a" * 64) -> SourceSnapshot:
    row = SourceSnapshot(
        source_key="test_source",
        source_url="https://example.test/snap",
        fetched_at=datetime.now(timezone.utc),
        content_hash=content_hash,
        raw_content="fixture",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _evidence(
    db_session,
    *,
    review_status: str = "verified_court_record",
    public_visibility: bool = True,
    verification_status: str = "verified",
    relationship_status: str = "active",
    snapshot_id: int | None = None,
) -> RelationshipEvidence:
    row = RelationshipEvidence(
        from_entity_type="crime_incident",
        from_entity_id=1,
        to_entity_type="event",
        to_entity_id=1,
        relationship_type="linked",
        evidence_type="report",
        evidence_source="fixture",
        extracted_by="test",
        confidence=0.9,
        public_visibility=public_visibility,
        review_status=review_status,
        verification_status=verification_status,
        relationship_status=relationship_status,
        evidence_snapshot_id=snapshot_id,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_public_review_status_blocked_when_verification_rejected(db_session):
    snap = _snapshot(db_session)
    evidence = _evidence(
        db_session,
        verification_status="rejected",
        relationship_status="active",
        snapshot_id=snap.id,
    )

    decision = can_show_public_entity(db_session, "relationship_evidence", evidence)
    assert decision.allowed is False
    assert any("verification_blocked:rejected" in r for r in decision.reasons)


def test_public_review_status_blocked_when_relationship_disputed(db_session):
    snap = _snapshot(db_session)
    evidence = _evidence(
        db_session,
        verification_status="verified",
        relationship_status="disputed",
        snapshot_id=snap.id,
    )

    decision = can_show_public_entity(db_session, "relationship_evidence", evidence)
    assert decision.allowed is False
    assert any("status_blocked:disputed" in r for r in decision.reasons)


def test_public_review_status_blocked_when_relationship_removed(db_session):
    snap = _snapshot(db_session)
    evidence = _evidence(
        db_session,
        verification_status="verified",
        relationship_status="removed",
        snapshot_id=snap.id,
    )

    decision = can_show_public_entity(db_session, "relationship_evidence", evidence)
    assert decision.allowed is False
    assert any("status_blocked:removed" in r for r in decision.reasons)


def test_verified_active_valid_snapshot_and_public_fields_allowed(db_session):
    snap = _snapshot(db_session)
    evidence = _evidence(
        db_session,
        review_status="verified_court_record",
        public_visibility=True,
        verification_status="verified",
        relationship_status="active",
        snapshot_id=snap.id,
    )

    publish = can_publish_entity(db_session, "relationship_evidence", evidence)
    show = can_show_public_entity(db_session, "relationship_evidence", evidence)
    assert publish.allowed is True
    assert show.allowed is True


def test_pending_private_relationship_evidence_is_blocked(db_session):
    snap = _snapshot(db_session)
    evidence = _evidence(
        db_session,
        review_status="pending_review",
        public_visibility=False,
        verification_status="pending",
        relationship_status="pending",
        snapshot_id=snap.id,
    )

    publish = can_publish_entity(db_session, "relationship_evidence", evidence)
    show = can_show_public_entity(db_session, "relationship_evidence", evidence)
    assert publish.allowed is False
    assert show.allowed is False
