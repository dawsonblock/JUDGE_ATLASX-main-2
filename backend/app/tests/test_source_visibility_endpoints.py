from __future__ import annotations

from uuid import uuid4

from app.db.session import SessionLocal
from app.auth.jwt_handler import create_access_token
from app.models.entities import SourceRegistry


def _seed_source(**overrides):
    key = overrides.pop("source_key", f"src_{uuid4().hex[:10]}")
    row = SourceRegistry(
        source_key=key,
        source_name=overrides.pop("source_name", f"Source {key}"),
        source_type=overrides.pop("source_type", "court_record"),
        source_tier=overrides.pop("source_tier", "official"),
        is_active=overrides.pop("is_active", False),
        source_class=overrides.pop("source_class", "machine_ingest"),
        automation_status=overrides.pop("automation_status", "machine_ready_disabled"),
        lifecycle_state=overrides.pop("lifecycle_state", "runnable_disabled"),
        **overrides,
    )
    with SessionLocal() as db:
        db.add(row)
        db.commit()


def _admin_headers() -> dict[str, str]:
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_admin_sources_include_source_status(client) -> None:
    _seed_source(source_key=f"admin_status_{uuid4().hex[:8]}")
    resp = client.get("/api/admin/sources", headers=_admin_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload
    assert "source_status" in payload[0]


def test_public_status_endpoint_returns_safe_subset(client) -> None:
    key = f"public_status_{uuid4().hex[:8]}"
    _seed_source(source_key=key, admin_notes="internal only", config_json='{"secret":true}')

    resp = client.get("/api/v1/sources/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    row = next(item for item in data["items"] if item["source_key"] == key)
    assert "admin_notes" not in row
    assert "config_json" not in row


def test_public_status_derives_runnable_from_lifecycle(client) -> None:
    key = f"runnable_{uuid4().hex[:8]}"
    _seed_source(
        source_key=key,
        lifecycle_state="runnable",
        automation_status="machine_ready_enabled",
        source_class="machine_ingest",
    )

    resp = client.get("/api/v1/sources/status")
    assert resp.status_code == 200
    row = next(item for item in resp.json()["items"] if item["source_key"] == key)
    assert row["source_status"] == "runnable"


def test_public_status_filters_by_source_status(client) -> None:
    key = f"portal_{uuid4().hex[:8]}"
    _seed_source(
        source_key=key,
        source_class="portal_reference",
        automation_status="adapter_missing",
        lifecycle_state="portal_reference",
    )

    resp = client.get("/api/v1/sources/status?source_status=portal_reference")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["source_key"] == key for item in items)
    assert all(item["source_status"] == "portal_reference" for item in items)


def test_public_status_filters_by_lifecycle_state(client) -> None:
    key = f"disabled_{uuid4().hex[:8]}"
    _seed_source(
        source_key=key,
        source_class="disabled_stub",
        automation_status="disabled_stub",
        lifecycle_state="disabled_stub",
    )

    resp = client.get("/api/v1/sources/status?lifecycle_state=disabled_stub")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["source_key"] == key for item in items)
    assert all(item["lifecycle_state"] == "disabled_stub" for item in items)
