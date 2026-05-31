from __future__ import annotations

from types import SimpleNamespace


def test_alpha_readiness_reports_public_platform_disabled(client) -> None:
    response = client.get("/api/v1/status/alpha-readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["public_platform"] == "disabled"


def test_alpha_readiness_warns_when_public_platform_enabled(
    client,
    monkeypatch,
    tmp_path,
) -> None:
    from app.api.routes import status as status_routes

    fake_settings = SimpleNamespace(
        app_env="development",
        runtime_profile="test",
        evidence_store_required=False,
        enable_experimental_live_map=False,
        enable_public_platform=True,
        enable_workflow_admin=False,
        evidence_store_root=str(tmp_path / "evidence"),
        enable_admin_review=False,
        storage_backend="local",
        ingestion_queue_backend="inprocess",
        rate_limit_backend="memory",
    )
    monkeypatch.setattr(status_routes, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(status_routes, "_repo_root", lambda: tmp_path)

    response = client.get("/api/v1/status/alpha-readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["public_platform"] == "enabled"
    assert "public_platform_enabled" in payload["warnings"]