"""HTTP proofs for reviewer/source-admin authority on AI source processing."""

from __future__ import annotations

from types import SimpleNamespace

from app.auth.jwt_handler import create_access_token


def _jwt_headers(role: str) -> dict[str, str]:
    token = create_access_token(email=f"{role}@example.test", role=role)
    return {"Authorization": f"Bearer {token}"}


def _settings():
    return SimpleNamespace(
        enable_admin_imports=True,
        enable_admin_review=True,
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        enforce_jwt_mutations=True,
        admin_token="test-token",
        admin_review_token="test-token",
    )


def test_ai_process_source_rejects_viewer_and_shared_token(client, monkeypatch):
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", _settings)

    response = client.post(
        "/api/admin/ai/process-source/nonexistent-source",
        headers=_jwt_headers("viewer"),
    )
    assert response.status_code == 403

    response = client.post(
        "/api/admin/ai/process-source/nonexistent-source",
        headers={"X-JTA-Admin-Token": "test-token"},
    )
    assert response.status_code == 403


def test_ai_process_source_allows_reviewer_and_source_admin_jwt(client, monkeypatch):
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", _settings)

    for role in ("reviewer", "source_admin"):
        response = client.post(
            "/api/admin/ai/process-source/nonexistent-source",
            headers=_jwt_headers(role),
        )
        assert response.status_code == 404
