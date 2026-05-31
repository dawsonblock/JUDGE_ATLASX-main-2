"""Tests for memory rebuild accumulation and snapshot scoping.

Verifies that:
- _get_latest_snapshot_for_entity returns None when no EntityEvidenceLink exists for the entity
- _get_latest_snapshot_for_entity returns the latest linked snapshot for the entity
- _upsert_claims accumulates a new MemoryEvidenceLink when the claim already exists
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.memory.rebuild import _get_latest_snapshot_for_entity, _upsert_claims
from app.models.entities import (
    CanonicalEntity,
    EntityEvidenceLink,
    MemoryClaim,
    MemoryEvidenceLink,
    MemoryRebuildRun,
    SourceRegistry,
    SourceSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_registry(db: Session, key: str) -> SourceRegistry:
    reg = db.query(SourceRegistry).filter_by(source_key=key).first()
    if reg:
        return reg
    reg = SourceRegistry(
        source_key=key,
        source_name=key,
        source_tier="court_direct",
        is_active=True,
        requires_manual_review=False,
        auto_publish_enabled=False,
    )
    db.add(reg)
    db.flush()
    return reg


def _make_entity(db: Session, label: str) -> CanonicalEntity:
    e = CanonicalEntity(
        entity_type="judge",
        canonical_name=f"Test Judge {label}",
        confidence_score=0.9,
    )
    db.add(e)
    db.flush()
    return e


def _make_snapshot(db: Session, source_key: str, offset: int = 0) -> SourceSnapshot:
    snap = SourceSnapshot(
        source_key=source_key,
        source_url=f"https://example.com/{source_key}/{offset}",
        fetched_at=datetime.datetime.utcnow() + datetime.timedelta(seconds=offset),
        content_hash="deadbeef",
        http_status=200,
        is_truncated=False,
        storage_backend="memory",
        original_content_hash="deadbeef",
    )
    db.add(snap)
    db.flush()
    return snap


def _make_rebuild_run(db: Session) -> MemoryRebuildRun:
    run = MemoryRebuildRun(rebuild_reason="test", status="running")
    db.add(run)
    db.flush()
    return run


# ---------------------------------------------------------------------------
# _get_latest_snapshot_for_entity
# ---------------------------------------------------------------------------

class TestGetLatestSnapshotForEntity:
    def test_returns_none_when_no_links(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "no_links")
            db.commit()
            result = _get_latest_snapshot_for_entity(db, entity.id)
        assert result is None

    def test_returns_linked_snapshot(self) -> None:
        with SessionLocal() as db:
            _make_source_registry(db, "eel_test_src")
            entity = _make_entity(db, "with_link")
            snap = _make_snapshot(db, "eel_test_src", offset=0)
            link = EntityEvidenceLink(
                entity_id=entity.id,
                snapshot_id=snap.id,
                linking_reason="test",
            )
            db.add(link)
            db.commit()
            result = _get_latest_snapshot_for_entity(db, entity.id)
        assert result is not None
        assert result.id == snap.id

    def test_returns_latest_when_multiple_links(self) -> None:
        with SessionLocal() as db:
            _make_source_registry(db, "eel_multi_src")
            entity = _make_entity(db, "multi_snap")
            snap_old = _make_snapshot(db, "eel_multi_src", offset=0)
            snap_new = _make_snapshot(db, "eel_multi_src", offset=999)
            for snap in (snap_old, snap_new):
                db.add(EntityEvidenceLink(entity_id=entity.id, snapshot_id=snap.id))
            db.commit()
            result = _get_latest_snapshot_for_entity(db, entity.id)
        assert result is not None
        assert result.id == snap_new.id

    def test_does_not_return_other_entity_snapshot(self) -> None:
        """Snapshot linked to a different entity must not be returned."""
        with SessionLocal() as db:
            _make_source_registry(db, "eel_scope_src")
            entity_a = _make_entity(db, "scope_a")
            entity_b = _make_entity(db, "scope_b")
            snap = _make_snapshot(db, "eel_scope_src", offset=0)
            # Link snapshot only to entity_b
            db.add(EntityEvidenceLink(entity_id=entity_b.id, snapshot_id=snap.id))
            db.commit()
            result = _get_latest_snapshot_for_entity(db, entity_a.id)
        assert result is None


# ---------------------------------------------------------------------------
# _upsert_claims accumulation
# ---------------------------------------------------------------------------

class TestUpsertClaimsAccumulation:
    def test_accumulates_evidence_link_for_existing_claim(self) -> None:
        """When claim already exists, a second snapshot should add a MemoryEvidenceLink."""
        with SessionLocal() as db:
            _make_source_registry(db, "accum_src")
            entity = _make_entity(db, "accum_entity")
            snap1 = _make_snapshot(db, "accum_src", offset=0)
            snap2 = _make_snapshot(db, "accum_src", offset=1)
            run = _make_rebuild_run(db)

            raw_claims = [
                {
                    "claim_type": "ruling",
                    "claim_value": "granted motion",
                    "confidence": 0.85,
                }
            ]
            # First call — creates the claim and its initial MemoryEvidenceLink
            _upsert_claims(db, entity.id, raw_claims, snap1, run.id)
            claim_id_before = db.query(MemoryClaim).filter_by(entity_id=entity.id).first().id
            link_count_before = (
                db.query(MemoryEvidenceLink).filter_by(claim_id=claim_id_before).count()
            )

            # Second call with different snapshot — must accumulate another link
            _upsert_claims(db, entity.id, raw_claims, snap2, run.id)
            db.commit()
            link_count_after = (
                db.query(MemoryEvidenceLink).filter_by(claim_id=claim_id_before).count()
            )

        assert link_count_before >= 1
        assert link_count_after == link_count_before + 1

    def test_does_not_duplicate_link_for_same_snapshot(self) -> None:
        """Same snapshot called twice must not create duplicate MemoryEvidenceLink."""
        with SessionLocal() as db:
            _make_source_registry(db, "nodup_src")
            entity = _make_entity(db, "nodup_entity")
            snap = _make_snapshot(db, "nodup_src", offset=0)
            run = _make_rebuild_run(db)

            raw_claims = [{"claim_type": "ruling", "claim_value": "denied", "confidence": 0.9}]
            _upsert_claims(db, entity.id, raw_claims, snap, run.id)
            _upsert_claims(db, entity.id, raw_claims, snap, run.id)
            db.commit()

            claim = db.query(MemoryClaim).filter_by(entity_id=entity.id).first()
            links = db.query(MemoryEvidenceLink).filter_by(
                claim_id=claim.id, snapshot_id=snap.id
            ).count()

        assert links == 1
