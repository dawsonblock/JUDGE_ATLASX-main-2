"""HTTP proofs for source-admin import authority on admin import routes."""

from __future__ import annotations

from types import SimpleNamespace

from app.auth.jwt_handler import create_access_token


def _jwt_headers(role: str) -> dict[str, str]:
    token = create_access_token(email=f"{role}@example.test", role=role)
    return {"Authorization": f"Bearer {token}"}


def _settings():
    return SimpleNamespace(
        enable_admin_imports=True,
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        enforce_jwt_mutations=True,
        admin_token="test-token",
        admin_review_token="test-token",
        max_csv_upload_size=1024 * 1024,
        max_csv_rows=10_000,
    )


def test_manual_csv_rejects_viewer_reviewer_and_shared_token(client, monkeypatch):
    import app.auth.admin as auth_admin
    import app.api.routes.ingestion as ingestion_routes

    monkeypatch.setattr(auth_admin, "get_settings", _settings)
    monkeypatch.setattr(ingestion_routes, "get_settings", _settings)

    sample_file = {"file": ("sample.csv", b"incident_type\nexample\n", "text/csv")}

    for role in ("viewer", "reviewer"):
        response = client.post(
            "/api/admin/import/crime-incidents/manual-csv",
            files=sample_file,
            headers=_jwt_headers(role),
        )
        assert response.status_code == 403

    response = client.post(
        "/api/admin/import/crime-incidents/manual-csv",
        files=sample_file,
        headers={"X-JTA-Admin-Token": "test-token"},
    )
    assert response.status_code == 403


def test_manual_csv_allows_source_admin_jwt(client, monkeypatch):
    import app.auth.admin as auth_admin
    import app.api.routes.ingestion as ingestion_routes

    monkeypatch.setattr(auth_admin, "get_settings", _settings)
    monkeypatch.setattr(ingestion_routes, "get_settings", _settings)

    def _fake_import(db, csv_buffer, commit=True):
        return SimpleNamespace(
            read_count=1,
            persisted_count=1,
            skipped_count=0,
            error_count=0,
            errors=[],
        )

    monkeypatch.setattr(
        "app.ingestion.crime_sources.manual_csv.import_crime_incidents_csv",
        _fake_import,
    )

    response = client.post(
        "/api/admin/import/crime-incidents/manual-csv",
        files={"file": ("sample.csv", b"incident_type\nexample\n", "text/csv")},
        headers=_jwt_headers("source_admin"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["persisted_count"] == 1
    assert data["skipped_count"] == 0
