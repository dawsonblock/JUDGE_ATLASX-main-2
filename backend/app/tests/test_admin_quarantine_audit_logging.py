from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, IngestionRun

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    from app.auth.jwt_handler import create_access_token

    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_quarantine_release_emits_audit_log() -> None:
    with SessionLocal() as db:
        run = IngestionRun(
            source_name="_test_quarantine_audit",
            started_at=datetime.now(timezone.utc),
            status="failed",
            pipeline_stage="quarantine",
            quarantine_reason="test",
        )
        db.add(run)
        db.commit()
        run_id = run.id

    response = client.post(
        f"/api/admin/quarantine/{run_id}/release",
        headers=_admin_headers(),
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "quarantine.release",
                AuditLog.entity_id == str(run_id),
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_id == "admin@example.com"

        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
        db.commit()


def test_quarantine_release_fails_closed_when_audit_write_fails() -> None:
    with SessionLocal() as db:
        run = IngestionRun(
            source_name="_test_quarantine_audit_fail_closed",
            started_at=datetime.now(timezone.utc),
            status="failed",
            pipeline_stage="quarantine",
            quarantine_reason="test",
        )
        db.add(run)
        db.commit()
        run_id = run.id

    with patch(
        "app.api.routes.admin_quarantine.log_mutation",
        side_effect=RuntimeError("audit down"),
    ):
        response = client.post(
            f"/api/admin/quarantine/{run_id}/release",
            headers=_admin_headers(),
        )

    assert response.status_code == 500, response.text
    assert response.json()["detail"] == "Audit logging failed; mutation aborted"

    with SessionLocal() as db:
        refreshed = db.get(IngestionRun, run_id)
        assert refreshed is not None
        assert refreshed.pipeline_stage == "quarantine"
        assert refreshed.status == "failed"

        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
        db.commit()
