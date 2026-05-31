"""Tests the evidence guard: approving an entity without a linked SourceSnapshot
that has a valid content_hash must return HTTP 422.

Three cases are tested:
  1. Entity has no source_snapshot_id at all → 422.
  2. Entity has a snapshot whose content_hash is empty ("") → 422.
  3. Entity has a snapshot with a real content_hash → 200 (guard passes).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.auth.jwt_handler import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import CrimeIncident, SourceSnapshot


_FAKE_HASH = "a" * 64  # 64-char hex-like string


@pytest.fixture()
def reviewer_client():
    import app.auth.admin as auth_admin

    class Settings:
        enable_admin_review = True
        enable_admin_imports = False
        jwt_auth_enabled = True
        enable_legacy_admin_token = False

    auth_admin.get_settings = lambda: Settings()
    yield TestClient(app)


def _reviewer_headers() -> dict[str, str]:
    token = create_access_token(email="evidence-guard-test@example.com", role="reviewer")
    return {"Authorization": f"Bearer {token}"}


def _make_incident(source_name: str, snapshot_id: int | None = None) -> int:
    """Insert a CrimeIncident; return its DB id."""
    with SessionLocal() as db:
        inc = CrimeIncident(
            incident_type="test_evidence_guard",
            incident_category="test",
            source_name=source_name,
            review_status="pending_review",
            source_snapshot_id=snapshot_id,
            latitude_public=52.13,
            longitude_public=-106.67,
            precision_level="city_centroid",
        )
        db.add(inc)
        db.commit()
        db.refresh(inc)
        return inc.id


def _make_snapshot(content_hash: str) -> int:
    """Insert a SourceSnapshot; return its DB id."""
    with SessionLocal() as db:
        snap = SourceSnapshot(
            source_url="https://example.com/evidence-guard-test",
            fetched_at=datetime.now(timezone.utc),
            content_hash=content_hash,
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap.id


def _delete_incident(entity_id: int) -> None:
    with SessionLocal() as db:
        inc = db.get(CrimeIncident, entity_id)
        if inc:
            db.delete(inc)
            db.commit()


def _delete_snapshot(snap_id: int) -> None:
    with SessionLocal() as db:
        snap = db.get(SourceSnapshot, snap_id)
        if snap:
            db.delete(snap)
            db.commit()


class TestEvidenceGuard:
    """Evidence snapshot check blocks approvals without valid content_hash."""

    def test_approve_without_snapshot_returns_422(
        self, reviewer_client: TestClient
    ) -> None:
        """Approving an entity that has no linked snapshot raises 422."""
        entity_id = _make_incident(
            source_name="ev_guard_no_snap_test",
            snapshot_id=None,
        )
        try:
            resp = reviewer_client.post(
                f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
                json={"decision": "approve"},
                headers=_reviewer_headers(),
            )
            assert resp.status_code == 422, resp.text
            assert "Evidence snapshot" in resp.json().get("detail", ""), resp.text
        finally:
            _delete_incident(entity_id)

    def test_approve_with_empty_hash_returns_422(
        self, reviewer_client: TestClient
    ) -> None:
        """Approving an entity whose linked snapshot has empty content_hash raises 422."""
        snap_id = _make_snapshot(content_hash="")
        entity_id = _make_incident(
            source_name="ev_guard_empty_hash_test",
            snapshot_id=snap_id,
        )
        try:
            resp = reviewer_client.post(
                f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
                json={"decision": "approve"},
                headers=_reviewer_headers(),
            )
            assert resp.status_code == 422, resp.text
            assert "Evidence snapshot" in resp.json().get("detail", ""), resp.text
        finally:
            _delete_incident(entity_id)
            _delete_snapshot(snap_id)

    def test_approve_with_valid_snapshot_succeeds(
        self, reviewer_client: TestClient
    ) -> None:
        """Approving an entity with a proper content_hash snapshot must pass the guard."""
        snap_id = _make_snapshot(content_hash=_FAKE_HASH)
        entity_id = _make_incident(
            source_name="ev_guard_valid_snap_test",
            snapshot_id=snap_id,
        )
        try:
            resp = reviewer_client.post(
                f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
                json={"decision": "approve"},
                headers=_reviewer_headers(),
            )
            assert resp.status_code == 200, resp.text
        finally:
            _delete_incident(entity_id)
            _delete_snapshot(snap_id)

    def test_reject_without_snapshot_is_allowed(
        self, reviewer_client: TestClient
    ) -> None:
        """Rejecting an entity never needs an evidence snapshot (guard only blocks publish)."""
        entity_id = _make_incident(
            source_name="ev_guard_reject_no_snap_test",
            snapshot_id=None,
        )
        try:
            resp = reviewer_client.post(
                f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
                json={"decision": "reject"},
                headers=_reviewer_headers(),
            )
            assert resp.status_code == 200, resp.text
        finally:
            _delete_incident(entity_id)
