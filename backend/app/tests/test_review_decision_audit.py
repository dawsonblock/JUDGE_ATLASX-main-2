"""Tests that admin_review_decision records the real actor in AuditLog.

Mocks the AI-review authority dependency via FastAPI dependency_overrides so
tests run without a real JWT; verifies actor_id, actor_type, and actor_role
fields on the resulting AuditLog row match the injected AdminActor identity.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.actor import AdminActor
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, CrimeIncident, SourceSnapshot
from app.security.import_authority import require_ai_review_actor


ACTOR = AdminActor(
    actor_id="reviewer@test.example",
    actor_type="user",
    role="reviewer",
    auth_method="jwt",
    email="reviewer@test.example",
)


@pytest.fixture()
def client_with_actor():
    """TestClient with require_ai_review_actor overridden to return ACTOR."""
    app.dependency_overrides[require_ai_review_actor] = lambda: ACTOR
    yield TestClient(app)
    app.dependency_overrides.pop(require_ai_review_actor, None)


def _first_crime_incident(db: Session) -> CrimeIncident | None:
    return db.scalar(select(CrimeIncident).order_by(CrimeIncident.id).limit(1))


def _attach_snapshot(db: Session, incident: CrimeIncident) -> None:
    if incident.source_snapshot_id:
        snap = db.get(SourceSnapshot, incident.source_snapshot_id)
        if snap is not None and snap.content_hash:
            return

    snap = SourceSnapshot(
        source_url="https://example.com/review-decision-audit",
        fetched_at=datetime.now(timezone.utc),
        content_hash="a" * 64,
    )
    db.add(snap)
    db.flush()
    incident.source_snapshot_id = snap.id
    db.commit()


class TestAdminReviewDecisionAudit:
    """Audit log attribution for review decisions."""

    def test_actor_id_recorded_in_audit_log(self, client_with_actor: TestClient) -> None:
        """AuditLog row must carry the injected actor_id, not the hardcoded 'admin'."""
        with SessionLocal() as db:
            incident = _first_crime_incident(db)
            if incident is None:
                pytest.skip("No CrimeIncident rows in test DB — seed required.")
            _attach_snapshot(db, incident)
            entity_id = str(incident.id)

        resp = client_with_actor.post(
            f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
            json={"decision": "approve", "notes": "audit-test"},
        )
        assert resp.status_code == 200, resp.text

        with SessionLocal() as db:
            log = db.scalar(
                select(AuditLog)
                .where(AuditLog.action == "review.decision")
                .where(AuditLog.entity_id == entity_id)
                .order_by(AuditLog.id.desc())
                .limit(1)
            )

        assert log is not None, "Expected an AuditLog row to be created"
        assert log.actor_id == ACTOR.actor_id
        assert log.actor_type == ACTOR.actor_type
        assert log.actor_role == ACTOR.role

    def test_actor_id_not_hardcoded_admin(self, client_with_actor: TestClient) -> None:
        """Regression: actor_id must never be the literal string 'admin'."""
        with SessionLocal() as db:
            incident = _first_crime_incident(db)
            if incident is None:
                pytest.skip("No CrimeIncident rows in test DB — seed required.")
            _attach_snapshot(db, incident)
            entity_id = str(incident.id)

        resp = client_with_actor.post(
            f"/api/admin/review-queue/crime_incident/{entity_id}/decision",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200, resp.text

        with SessionLocal() as db:
            log = db.scalar(
                select(AuditLog)
                .where(AuditLog.action == "review.decision")
                .where(AuditLog.entity_id == entity_id)
                .order_by(AuditLog.id.desc())
                .limit(1)
            )

        assert log is not None
        assert log.actor_id != "admin", (
            "actor_id must be the authenticated identity, not the hardcoded sentinel 'admin'"
        )
