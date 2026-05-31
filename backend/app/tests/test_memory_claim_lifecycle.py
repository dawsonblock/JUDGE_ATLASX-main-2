"""Tests for MemoryClaim lifecycle fields and invalidation.

Verifies that:
- MemoryClaim.status defaults to "active"
- invalidate_claim sets both is_active=False and status="inactive"
- invalidate_entity_state sets status="inactive" on all claims for an entity
- get_active_claims excludes claims with status != "active"
"""
from __future__ import annotations

import datetime

import pytest

from app.db.session import SessionLocal
from app.memory.invalidation import invalidate_claim, invalidate_entity_state
from app.memory.retrieval import get_active_claims
from app.models.entities import (
    CanonicalEntity,
    MemoryClaim,
    MemoryEntityState,
    MemoryRebuildRun,
    SourceRegistry,
    SourceSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        canonical_name=f"Lifecycle Judge {label}",
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


def _make_claim(db, entity_id: int, *, status: str = "active") -> MemoryClaim:
    claim = MemoryClaim(
        entity_id=entity_id,
        claim_type="ruling",
        claim_value="test ruling",
        confidence=0.8,
        is_active=True,
        status=status,
    )
    db.add(claim)
    db.flush()
    return claim


def _make_entity_state(db, entity_id: int, run_id: int) -> MemoryEntityState:
    state = MemoryEntityState(
        entity_id=entity_id,
        display_name="Test Entity",
        state_checksum="abc123",
        last_rebuild_run_id=run_id,
        rebuilt_at=datetime.datetime.utcnow(),
    )
    db.add(state)
    db.flush()
    return state


def _make_run(db) -> MemoryRebuildRun:
    run = MemoryRebuildRun(rebuild_reason="lifecycle_test", status="running")
    db.add(run)
    db.flush()
    return run


# ---------------------------------------------------------------------------
# ORM defaults
# ---------------------------------------------------------------------------

class TestMemoryClaimDefaults:
    def test_status_defaults_to_active(self) -> None:
        with SessionLocal() as db:
            _make_source(db, "lc_default_src")
            entity = _make_entity(db, "defaults")
            claim = MemoryClaim(
                entity_id=entity.id,
                claim_type="ruling",
                claim_value="default status check",
                confidence=0.75,
                is_active=True,
            )
            db.add(claim)
            db.commit()
            db.refresh(claim)

        assert claim.status == "active"

    def test_last_seen_at_is_nullable(self) -> None:
        with SessionLocal() as db:
            _make_source(db, "lc_nullable_src")
            entity = _make_entity(db, "nullable_last_seen")
            claim = MemoryClaim(
                entity_id=entity.id,
                claim_type="ruling",
                claim_value="nullable check",
                confidence=0.75,
                is_active=True,
            )
            db.add(claim)
            db.commit()
            db.refresh(claim)

        assert claim.last_seen_at is None


# ---------------------------------------------------------------------------
# invalidate_claim
# ---------------------------------------------------------------------------

class TestInvalidateClaim:
    def test_sets_is_active_false(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "inv_single")
            claim = _make_claim(db, entity.id)
            db.commit()
            claim_id = claim.id

            invalidate_claim(claim_id, "unit test invalidation", db)
            db.commit()

            refreshed = db.get(MemoryClaim, claim_id)
        assert refreshed.is_active is False

    def test_sets_status_inactive(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "inv_status")
            claim = _make_claim(db, entity.id)
            db.commit()
            claim_id = claim.id

            invalidate_claim(claim_id, "status field test", db)
            db.commit()

            refreshed = db.get(MemoryClaim, claim_id)
        assert refreshed.status == "inactive"

    def test_sets_invalidation_reason(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "inv_reason")
            claim = _make_claim(db, entity.id)
            db.commit()
            claim_id = claim.id

            invalidate_claim(claim_id, "reason_probe_xyz", db)
            db.commit()

            refreshed = db.get(MemoryClaim, claim_id)
        assert refreshed.invalidation_reason == "reason_probe_xyz"


# ---------------------------------------------------------------------------
# invalidate_entity_state
# ---------------------------------------------------------------------------

class TestInvalidateEntityState:
    def test_all_claims_set_inactive(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "inv_entity_all")
            run = _make_run(db)
            _make_entity_state(db, entity.id, run.id)
            claim_a = _make_claim(db, entity.id)
            claim_b = _make_claim(db, entity.id)
            db.commit()
            e_id = entity.id

            invalidate_entity_state(e_id, "bulk invalidation test", db)
            db.commit()

            claims = db.query(MemoryClaim).filter_by(entity_id=e_id).all()

        for c in claims:
            assert c.status == "inactive", f"Claim {c.id} should be inactive"
            assert c.is_active is False


# ---------------------------------------------------------------------------
# get_active_claims filtering
# ---------------------------------------------------------------------------

class TestGetActiveClaims:
    def test_excludes_inactive_status(self) -> None:
        with SessionLocal() as db:
            entity = _make_entity(db, "retrieval_filter")
            active_claim = _make_claim(db, entity.id, status="active")
            inactive_claim = _make_claim(db, entity.id, status="inactive")
            inactive_claim.is_active = False
            db.commit()
            e_id = entity.id
            active_id = active_claim.id
            inactive_id = inactive_claim.id

            results = get_active_claims(e_id, db)
            result_ids = [r.id for r in results]

        assert active_id in result_ids
        assert inactive_id not in result_ids

    def test_excludes_is_active_false(self) -> None:
        """Claim with is_active=False but status='active' should still be excluded."""
        with SessionLocal() as db:
            entity = _make_entity(db, "retrieval_is_active")
            inconsistent = MemoryClaim(
                entity_id=entity.id,
                claim_type="ruling",
                claim_value="inconsistent state",
                confidence=0.6,
                is_active=False,
                status="active",
            )
            db.add(inconsistent)
            db.commit()
            e_id = entity.id
            inconsistent_id = inconsistent.id

            results = get_active_claims(e_id, db)
            result_ids = [r.id for r in results]

        assert inconsistent_id not in result_ids
