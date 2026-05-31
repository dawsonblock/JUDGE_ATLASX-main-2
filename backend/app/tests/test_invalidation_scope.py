"""Phase 8: Scope-boundary tests for invalidate_claim().

Verifies that edge retraction is strictly limited to:
  1. Edges whose source_snapshot_id matches the claim's snapshot (other snapshots safe).
  2. Edges whose subject_id matches the claim's entity (other entities safe).
  3. Edges where the claim entity is the object_id are NOT retracted (design boundary).
  4. No edges are retracted when the claim has no snapshot link.
"""
from __future__ import annotations

import datetime
from datetime import timezone

import pytest

from app.db.session import SessionLocal
from app.memory.invalidation import invalidate_claim
from app.models.entities import (
    CanonicalEntity,
    EntityGraphEdge,
    MemoryClaim,
    SourceRegistry,
    SourceSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRED = "_scope_test_pred"  # sentinel predicate for cleanup


def _make_source(db, key: str) -> SourceRegistry:
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


def _make_entity(db, label: str) -> CanonicalEntity:
    e = CanonicalEntity(
        entity_type="judge",
        canonical_name=f"Scope Test Entity {label}",
        confidence_score=0.9,
    )
    db.add(e)
    db.flush()
    return e


def _make_snapshot(db, source_key: str) -> SourceSnapshot:
    snap = SourceSnapshot(
        source_key=source_key,
        source_url=f"https://example.com/{source_key}",
        fetched_at=datetime.datetime.utcnow(),
        content_hash="abcdef01",
        http_status=200,
        is_truncated=False,
        storage_backend="memory",
        original_content_hash="abcdef01",
    )
    db.add(snap)
    db.flush()
    return snap


def _make_claim(db, entity_id: int, snap_id: int | None = None) -> MemoryClaim:
    claim = MemoryClaim(
        entity_id=entity_id,
        source_snapshot_id=snap_id,
        claim_type="ruling",
        claim_value="scope test ruling",
        confidence=0.8,
        is_active=True,
        status="active",
    )
    db.add(claim)
    db.flush()
    return claim


def _make_edge(
    db,
    *,
    subject_id: int,
    object_id: int,
    snap_id: int | None = None,
    subject_type: str = "court",
    object_type: str = "court",
) -> EntityGraphEdge:
    edge = EntityGraphEdge(
        subject_type=subject_type,
        subject_id=subject_id,
        predicate=_PRED,
        object_type=object_type,
        object_id=object_id,
        source_snapshot_id=snap_id,
        status="active",
        created_by="test",
        valid_from=datetime.datetime.now(timezone.utc),
    )
    db.add(edge)
    db.flush()
    return edge


def _purge_test_edges(db) -> None:
    db.query(EntityGraphEdge).filter(
        EntityGraphEdge.predicate == _PRED
    ).delete(synchronize_session=False)
    db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInvalidateClaimEdgeScope:
    """Scope boundaries for the cascade edge retraction inside invalidate_claim()."""

    def test_edge_retraction_limited_to_matching_snapshot(self):
        """Edge with a DIFFERENT source_snapshot_id must remain active."""
        db = SessionLocal()
        try:
            _purge_test_edges(db)
            _make_source(db, "_scope_src_snap_A")
            _make_source(db, "_scope_src_snap_B")
            entity = _make_entity(db, "snap_scope")
            snap_a = _make_snapshot(db, "_scope_src_snap_A")
            snap_b = _make_snapshot(db, "_scope_src_snap_B")

            # The claim is linked to snap_a only
            claim = _make_claim(db, entity.id, snap_id=snap_a.id)

            # Edge from snap_a → should be retracted
            edge_a = _make_edge(
                db,
                subject_id=entity.id,
                object_id=entity.id + 9999,
                snap_id=snap_a.id,
            )
            # Edge from snap_b → should NOT be touched
            edge_b = _make_edge(
                db,
                subject_id=entity.id,
                object_id=entity.id + 9999,
                snap_id=snap_b.id,
            )

            db.commit()

            invalidate_claim(claim.id, "scope test", db)
            db.commit()

            db.refresh(edge_a)
            db.refresh(edge_b)

            assert edge_a.status == "retracted", "snap_a edge should be retracted"
            assert edge_b.status == "active", "snap_b edge must remain active"
        finally:
            _purge_test_edges(db)
            db.commit()
            db.close()

    def test_edge_retraction_limited_to_matching_subject(self):
        """Edge for a DIFFERENT entity's subject_id must remain active."""
        db = SessionLocal()
        try:
            _purge_test_edges(db)
            _make_source(db, "_scope_src_subj")
            entity1 = _make_entity(db, "subj_scope_1")
            entity2 = _make_entity(db, "subj_scope_2")
            snap = _make_snapshot(db, "_scope_src_subj")

            # Claim is for entity1
            claim = _make_claim(db, entity1.id, snap_id=snap.id)

            # Edge with entity1 as subject → should be retracted
            edge_e1 = _make_edge(
                db,
                subject_id=entity1.id,
                object_id=entity2.id,
                snap_id=snap.id,
            )
            # Edge with entity2 as subject (same snapshot) → should NOT be touched
            edge_e2 = _make_edge(
                db,
                subject_id=entity2.id,
                object_id=entity1.id,
                snap_id=snap.id,
            )

            db.commit()

            invalidate_claim(claim.id, "scope test", db)
            db.commit()

            db.refresh(edge_e1)
            db.refresh(edge_e2)

            assert edge_e1.status == "retracted", "entity1-subject edge should be retracted"
            assert edge_e2.status == "active", "entity2-subject edge must remain active"
        finally:
            _purge_test_edges(db)
            db.commit()
            db.close()

    def test_object_side_edge_not_retracted(self):
        """An edge where the invalidated entity is the OBJECT (not subject) is untouched."""
        db = SessionLocal()
        try:
            _purge_test_edges(db)
            _make_source(db, "_scope_src_obj")
            entity1 = _make_entity(db, "obj_scope_1")
            entity2 = _make_entity(db, "obj_scope_2")
            snap = _make_snapshot(db, "_scope_src_obj")

            # Claim is for entity1
            claim = _make_claim(db, entity1.id, snap_id=snap.id)

            # Edge where entity1 is the OBJECT, entity2 is the subject
            edge_obj_side = _make_edge(
                db,
                subject_id=entity2.id,
                object_id=entity1.id,   # entity1 is object here
                snap_id=snap.id,
            )

            db.commit()

            invalidate_claim(claim.id, "scope test", db)
            db.commit()

            db.refresh(edge_obj_side)

            assert edge_obj_side.status == "active", (
                "Object-side edges must not be retracted — "
                "invalidate_claim only retracts where subject_id == entity_id"
            )
        finally:
            _purge_test_edges(db)
            db.commit()
            db.close()

    def test_no_edge_retraction_when_snapshot_is_none(self):
        """When source_snapshot_id is None, the retraction block is skipped entirely."""
        db = SessionLocal()
        try:
            _purge_test_edges(db)
            entity = _make_entity(db, "no_snap_scope")

            # Claim without any snapshot link
            claim = _make_claim(db, entity.id, snap_id=None)

            # Edge with NULL snapshot for this entity
            edge_null_snap = _make_edge(
                db,
                subject_id=entity.id,
                object_id=entity.id + 9999,
                snap_id=None,
            )

            db.commit()

            invalidate_claim(claim.id, "scope test", db)
            db.commit()

            db.refresh(edge_null_snap)

            assert edge_null_snap.status == "active", (
                "No retraction should occur when claim.source_snapshot_id is None"
            )
        finally:
            _purge_test_edges(db)
            db.commit()
            db.close()
