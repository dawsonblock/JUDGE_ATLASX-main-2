from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    from app.auth.jwt_handler import create_access_token

    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_memory_rebuild_emits_audit_log() -> None:
    response = client.post(
        "/api/admin/memory/rebuild",
        json={"scope": "full"},
        headers=_admin_headers(),
    )
    assert response.status_code == 202, response.text

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "memory.rebuild.enqueue")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_id == "admin@example.com"
        assert audit.entity_type == "memory_rebuild"
