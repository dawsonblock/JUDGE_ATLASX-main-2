from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.jwt_handler import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import SourceRegistry


client = TestClient(app)


def _headers() -> dict[str, str]:
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_patch_cannot_activate_source() -> None:
    source_key = "test_patch_activate_block"
    with SessionLocal() as db:
        db.add(
            SourceRegistry(
                source_key=source_key,
                source_name="Patch Activate Block",
                source_type="legislation",
                source_class="machine_ingest",
                automation_status="machine_ready_disabled",
                is_active=False,
            )
        )
        db.commit()

    resp = client.patch(
        f"/api/admin/sources/{source_key}",
        headers=_headers(),
        json={"is_active": True},
    )
    assert resp.status_code == 422
    assert "Use /enable or /disable endpoints" in str(resp.json())

    with SessionLocal() as db:
        row = db.query(SourceRegistry).filter(SourceRegistry.source_key == source_key).first()
        assert row is not None
        assert row.is_active is False

    with SessionLocal() as db:
        db.query(SourceRegistry).filter(SourceRegistry.source_key == source_key).delete()
        db.commit()
