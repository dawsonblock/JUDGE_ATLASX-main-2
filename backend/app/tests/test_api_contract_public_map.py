"""Backend API contract smoke tests for public map endpoints."""

from __future__ import annotations


def test_api_contract_map_events_shape(client) -> None:
    response = client.get("/api/map/events")
    assert response.status_code == 200
    body = response.json()

    assert body.get("type") == "FeatureCollection"
    assert isinstance(body.get("features"), list)
    assert isinstance(body.get("returned_count"), int)
    assert isinstance(body.get("truncated"), bool)
    assert isinstance(body.get("filters_applied"), dict)
    assert isinstance(body.get("disclaimer"), str)


def test_api_contract_map_crime_incidents_shape(client) -> None:
    response = client.get("/api/map/crime-incidents")
    assert response.status_code == 200
    body = response.json()

    assert body.get("type") == "FeatureCollection"
    assert isinstance(body.get("features"), list)
    assert isinstance(body.get("returned_count"), int)
    assert isinstance(body.get("truncated"), bool)
    assert isinstance(body.get("filters_applied"), dict)
    assert isinstance(body.get("disclaimer"), str)
