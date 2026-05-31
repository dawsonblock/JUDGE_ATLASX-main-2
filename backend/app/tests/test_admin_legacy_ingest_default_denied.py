from __future__ import annotations

from types import SimpleNamespace

from app.auth.jwt_handler import create_access_token


def _jwt_headers(role: str) -> dict[str, str]:
    token = create_access_token(email=f"{role}@example.test", role=role)
    return {"Authorization": f"Bearer {token}"}


def _settings(*, legacy_enabled: bool):
    return SimpleNamespace(
        enable_admin_imports=True,
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        enforce_jwt_mutations=True,
        enable_legacy_us_ingest_routes=legacy_enabled,
        admin_token="test-token",
        admin_review_token="test-token",
        max_csv_upload_size=1024 * 1024,
        max_csv_rows=10_000,
    )


def test_legacy_us_ingest_route_denied_by_default(client, monkeypatch):
    import app.auth.admin as auth_admin
    import app.api.routes as routes

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _settings(legacy_enabled=False))
    monkeypatch.setattr(routes, "get_settings", lambda: _settings(legacy_enabled=False))

    response = client.post("/api/admin/ingest/fbi", json=[], headers=_jwt_headers("source_admin"))

    # Legacy router is conditionally registered at app startup.
    # Default-off posture should return 404 when route is not mounted.
    assert response.status_code == 404


def test_legacy_courtlistener_route_denied_by_default(client, monkeypatch):
    import app.auth.admin as auth_admin
    import app.api.routes as routes

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _settings(legacy_enabled=False))
    monkeypatch.setattr(routes, "get_settings", lambda: _settings(legacy_enabled=False))

    response = client.post(
        "/api/admin/ingest/courtlistener-bulk/list",
        headers=_jwt_headers("source_admin"),
    )

    assert response.status_code == 404
