from __future__ import annotations


def test_workflow_runs_requires_authentication(client):
    response = client.get("/api/admin/workflows/runs")
    assert response.status_code in (401, 403)


def test_workflow_schedules_requires_authentication(client):
    response = client.get("/api/admin/workflows/schedules")
    assert response.status_code in (401, 403)


def test_workflow_runs_static_route_not_captured(client, jwt_admin_headers):
    response = client.get(
        "/api/admin/workflows/runs",
        headers=jwt_admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)


def test_workflow_schedules_static_route_not_captured(
    client,
    jwt_admin_headers,
):
    response = client.get(
        "/api/admin/workflows/schedules",
        headers=jwt_admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "schedules" in body
    assert isinstance(body["schedules"], list)
