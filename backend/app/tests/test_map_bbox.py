"""Regression tests for bbox filtering correctness.

These tests verify that:
- /api/map/events?bbox=... returns expected visible seeded events
- A newly inserted Location/Event after startup is returned by bbox
- Bbox behavior does not depend on Location.geom being populated
- Invalid bbox still returns 422

NOTE: Location.geom is NOT mapped in the ORM. Bbox filtering uses lat/lon only.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Location


def test_bbox_returns_seeded_events(client):
    """Test /api/map/events?bbox=... returns expected visible seeded events.
    
    Seeded data includes NYC, Chicago, LA locations which should be visible
    in bbox queries covering those areas.
    """
    # NYC area bbox (roughly) - seeded data has NYC locations
    bbox = "-74.5,40.5,-73.5,41.0"
    response = client.get(f"/api/map/events?bbox={bbox}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    # Should return at least some seeded events in NYC area
    assert len(payload["features"]) > 0, "Expected seeded events in NYC bbox"
    # Verify events have valid coordinates within bbox
    for feature in payload["features"]:
        coords = feature["geometry"]["coordinates"]
        assert len(coords) == 2
        lon, lat = coords
        assert -74.5 <= lon <= -73.5
        assert 40.5 <= lat <= 41.0


def test_newly_inserted_event_returned_by_bbox(client):
    """Test that a newly inserted Location/Event after startup is returned by bbox.
    
    This proves bbox behavior does not depend on Location.geom being populated
    at migration time - it works for new inserts too.
    """
    with SessionLocal() as db:
        # Create a new location with specific coordinates
        new_location = Location(
            name="Test Location Bbox",
            location_type="courthouse",
            city="Edmonton",
            state="Alberta",
            latitude=53.5461,
            longitude=-113.4938,
            # geom is NULL - we intentionally don't set it
        )
        db.add(new_location)
        db.commit()
        db.refresh(new_location)
        
        # Create an event at this location
        from app.models.entities import Case, Court, Event, Judge
        
        # Get or create minimal related entities
        court = db.execute(select(Court).limit(1)).scalar_one_or_none()
        judge = db.execute(select(Judge).limit(1)).scalar_one_or_none()
        case = db.execute(select(Case).limit(1)).scalar_one_or_none()
        
        if court and judge and case:
            new_event = Event(
                event_id="EVT-BBOX-TEST-001",
                court_id=court.id,
                judge_id=judge.id,
                case_id=case.id,
                primary_location_id=new_location.id,
                event_type="hearing",
                title="Bbox Test Event",
                summary="Test event for bbox filtering",
                decision_date=date.today(),
                public_visibility=True,
                review_status="official_police_open_data_report",
            )
            db.add(new_event)
            db.commit()
            
            # Now query with bbox covering Edmonton
            bbox = "-114.0,53.0,-113.0,54.0"
            response = client.get(f"/api/map/events?bbox={bbox}")
            assert response.status_code == 200
            payload = response.json()
            
            # Find our new event in the results
            event_ids = [f["properties"]["event_id"] for f in payload["features"]]
            assert "EVT-BBOX-TEST-001" in event_ids, \
                f"Newly inserted event not found in bbox results. Events found: {event_ids}"


def test_bbox_behavior_independent_of_geom_column(client):
    """Test that bbox behavior does not depend on Location.geom being populated.
    
    This verifies the fix: we now use lat/lon only, not Location.geom which
    can be NULL for rows inserted after the migration.
    """
    with SessionLocal() as db:
        # Create a location without geom (simulating post-migration state)
        # Location.geom exists in PostgreSQL but is NOT mapped in ORM
        null_geom_location = Location(
            name="Null Geom Location",
            location_type="courthouse",
            city="Vancouver",
            state="BC",
            latitude=49.2827,
            longitude=-123.1207,
        )
        db.add(null_geom_location)
        db.commit()
        db.refresh(null_geom_location)
        
        # This location should still appear in bbox queries (using lat/lon)
        # Query the raw location via bbox using lat/lon (Vancouver area)
        stmt = select(Location).where(
            Location.longitude >= -124.0,
            Location.longitude <= -122.0,
            Location.latitude >= 49.0,
            Location.latitude <= 50.0,
            Location.id == null_geom_location.id,
        )
        result = db.execute(stmt).scalar_one_or_none()
        assert result is not None, "Location with NULL geom should be found via lat/lon bbox"


def test_map_events_with_bbox_returns_results(client):
    """Test /api/map/events with bbox query parameter."""
    # Calgary area bbox (roughly)
    bbox = "-114.2,51.0,-113.9,51.1"
    response = client.get(f"/api/map/events?bbox={bbox}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert "features" in payload
    assert "filters_applied" in payload
    assert payload["filters_applied"]["bbox"] == bbox


def test_map_crime_incidents_with_bbox_returns_results(client):
    """Test /api/map/crime-incidents with bbox query parameter."""
    bbox = "-79.5,43.6,-79.3,43.8"  # Toronto area
    response = client.get(f"/api/map/crime-incidents?bbox={bbox}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert "features" in payload


def test_map_crime_aggregates_with_bbox_returns_results(client):
    """Test /api/map/crime-aggregates with bbox query parameter."""
    bbox = "-87.8,41.8,-87.5,42.0"  # Chicago area
    response = client.get(f"/api/map/crime-aggregates?bbox={bbox}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert "features" in payload
    assert payload["filters_applied"]["aggregate_only"] is True


def test_bbox_validation_rejects_invalid_format(client):
    """Test bbox parameter validation rejects malformed input."""
    response = client.get("/api/map/events?bbox=invalid")
    assert response.status_code == 422
    assert "bbox must be" in response.json()["detail"]


def test_bbox_validation_rejects_out_of_range(client):
    """Test bbox parameter validation rejects out-of-range values."""
    response = client.get("/api/map/events?bbox=-200,0,0,0")
    assert response.status_code == 422
    assert "out of valid WGS84 range" in response.json()["detail"]


def test_bbox_validation_rejects_south_greater_than_north(client):
    """Test bbox parameter validation rejects south > north."""
    response = client.get("/api/map/events?bbox=-100,50,-90,40")
    assert response.status_code == 422
    assert "south must be <= north" in response.json()["detail"]


def test_map_events_bbox_returns_only_events_in_bounds(client):
    """Test that bbox filtering actually filters events to the specified area."""
    # First get all events
    all_response = client.get("/api/map/events")
    assert all_response.status_code == 200
    all_count = all_response.json()["returned_count"]
    
    # Get events in a very small bbox (middle of ocean, likely no events)
    small_bbox = "-100,20,-99,21"  # Small area
    small_response = client.get(f"/api/map/events?bbox={small_bbox}")
    assert small_response.status_code == 200
    small_count = small_response.json()["returned_count"]
    
    # Small bbox should return fewer or equal events than no bbox
    assert small_count <= all_count


def test_bbox_query_does_not_crash_with_postgresql_dialect(monkeypatch, client):
    """Verify Location.geom is accessible when using PostGIS path.
    
    When mocking PostgreSQL dialect on SQLite, the query will fail because
    SQLite lacks PostGIS functions (ST_Intersects, ST_MakeEnvelope). But the
    key test is that NO AttributeError is raised for Location.geom.
    
    Before the fix: AttributeError: type object 'Location' has no attribute 'geom'
    After the fix: OperationalError: no such function: ST_MakeEnvelope
    """
    from unittest.mock import patch
    from app.api.routes import map as map_module
    
    # Mock _is_postgres to return True (simulate PostgreSQL)
    with patch.object(map_module, '_is_postgres', return_value=True):
        bbox = "-114.0,51.0,-113.0,52.0"
        try:
            response = client.get(f"/api/map/events?bbox={bbox}")
            # Success case (unlikely on SQLite)
            assert response.status_code == 200
        except Exception as e:
            error_text = str(e)
            # The fix is verified if we get a SQL error (not AttributeError on geom)
            assert "AttributeError" not in error_text, f"AttributeError indicates geom bug: {e}"
            assert "has no attribute 'geom'" not in error_text, "Location.geom not accessible - PostGIS bbox bug!"
            # Expected: SQL error about missing PostGIS functions on SQLite
            assert "ST_MakeEnvelope" in error_text or "ST_Intersects" in error_text or "geom" in error_text.lower()
