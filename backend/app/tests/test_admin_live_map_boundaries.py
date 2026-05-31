from __future__ import annotations

from datetime import datetime, timezone

from app.models.geo_legal_event import GeoLegalEvent as GeoLegalEventModel


def _seed_admin_live_map_event(db_session) -> None:
    event = GeoLegalEventModel(
        id="admin-live-map-event-1",
        event_type="court_event",
        title="Admin Live Map Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        confidence=0.9,
        confidence_label="high",
        review_status="needs_review",
        publish_status="admin_only",
        source_ids=["source-admin-1"],
        evidence_ids=["evidence-admin-1"],
        claim_ids=["claim-admin-1"],
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()


def test_admin_live_map_requires_authenticated_actor(client, db_session):
    _seed_admin_live_map_event(db_session)
    response = client.get("/api/admin/live-map/events")
    assert response.status_code in (401, 403)


def test_admin_live_map_rejects_shared_token_only_auth(client, db_session):
    _seed_admin_live_map_event(db_session)
    response = client.get(
        "/api/admin/live-map/events",
        headers={"X-JTA-Admin-Token": "test-token"},
    )
    assert response.status_code == 403
    assert "JWT" in response.json()["detail"] or "Legacy shared-token" in response.json()["detail"]


def test_admin_live_map_allows_reviewer_or_admin_jwt(
    client, db_session, jwt_admin_headers
):
    _seed_admin_live_map_event(db_session)
    response = client.get("/api/admin/live-map/events", headers=jwt_admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["filters_applied"]["admin_mode"] is True
    assert body["returned_count"] >= 1
    assert any(event["id"] == "admin-live-map-event-1" for event in body["events"])


def test_admin_live_map_single_event_requires_jwt(
    client, db_session, jwt_admin_headers
):
    _seed_admin_live_map_event(db_session)

    forbidden = client.get(
        "/api/admin/live-map/events/admin-live-map-event-1",
        headers={"X-JTA-Admin-Token": "test-token"},
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/api/admin/live-map/events/admin-live-map-event-1",
        headers=jwt_admin_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["id"] == "admin-live-map-event-1"
