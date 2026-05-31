"""Tests for the /verify snapshot integrity endpoint.

Verifies:
- GET /api/admin/evidence-store/verify/{id} returns {"status": "ok"} when hash matches
- Returns {"status": "corrupted"} when hash mismatches
- Returns 404 for unknown snapshot id
- Returns {"status": "unavailable"} when content cannot be read
"""
from __future__ import annotations

import datetime
import hashlib

from fastapi.testclient import TestClient
from unittest.mock import patch

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import SourceRegistry, SourceSnapshot

client = TestClient(app)

def _jwt_admin_headers() -> dict[str, str]:
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}

ADMIN_HEADERS = _jwt_admin_headers()


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


def _make_snapshot(db, source_key: str, content: bytes) -> SourceSnapshot:
    digest = hashlib.sha256(content).hexdigest()
    snap = SourceSnapshot(
        source_key=source_key,
        source_url=f"https://example.com/verify/{source_key}",
        fetched_at=datetime.datetime.utcnow(),
        content_hash=digest,
        http_status=200,
        is_truncated=False,
        storage_backend="memory",
        original_content_hash=digest,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


class TestSnapshotVerifyEndpoint:
    def test_ok_when_content_matches_hash(self) -> None:
        content = b"valid snapshot content for verify test"
        digest = hashlib.sha256(content).hexdigest()

        with SessionLocal() as db:
            _make_source(db, "verify_ok_src")
            snap = _make_snapshot(db, "verify_ok_src", content)
            snap_id = snap.id

        mock_target = "app.api.routes.evidence_store.read_snapshot_content"
        with patch(mock_target, return_value=content):
            resp = client.get(
                f"/api/admin/evidence-store/verify/{snap_id}",
                headers=ADMIN_HEADERS,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["stored_hash"] == digest
        assert body["actual_hash"] == digest

    def test_corrupted_when_hash_mismatches(self) -> None:
        original_content = b"original snapshot bytes"
        digest = hashlib.sha256(original_content).hexdigest()
        corrupted_content = b"tampered snapshot bytes"

        with SessionLocal() as db:
            _make_source(db, "verify_corrupt_src")
            snap = _make_snapshot(db, "verify_corrupt_src", original_content)
            snap_id = snap.id

        mock_target = "app.api.routes.evidence_store.read_snapshot_content"
        with patch(mock_target, return_value=corrupted_content):
            resp = client.get(
                f"/api/admin/evidence-store/verify/{snap_id}",
                headers=ADMIN_HEADERS,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "corrupted"
        assert body["stored_hash"] == digest
        assert body["actual_hash"] != digest

    def test_unavailable_when_content_none(self) -> None:
        content = b"unavailable probe content"

        with SessionLocal() as db:
            _make_source(db, "verify_unavail_src")
            snap = _make_snapshot(db, "verify_unavail_src", content)
            snap_id = snap.id

        mock_target = "app.api.routes.evidence_store.read_snapshot_content"
        with patch(mock_target, return_value=None):
            resp = client.get(
                f"/api/admin/evidence-store/verify/{snap_id}",
                headers=ADMIN_HEADERS,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unavailable"

    def test_not_found_for_unknown_id(self) -> None:
        resp = client.get(
            "/api/admin/evidence-store/verify/999999999",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    def test_requires_admin_token(self) -> None:
        resp = client.get("/api/admin/evidence-store/verify/1")
        assert resp.status_code in (401, 403)
