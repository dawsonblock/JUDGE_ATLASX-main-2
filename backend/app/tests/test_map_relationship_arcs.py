"""Tests for GET /api/map/relationship-arcs (Phase 7 hardening)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Court, EntityGraphEdge, Location

client = TestClient(app)


@contextmanager
def _arcs_enabled_override(min_evidence: int = 0):
    """Temporarily override get_settings so arc feature flag is on."""

    def _override() -> Settings:
        return Settings(
            enable_public_relationship_arcs=True,
            public_relationship_arc_min_evidence=min_evidence,
        )

    app.dependency_overrides[get_settings] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


def _arc_cleanup(db) -> None:
    """Remove test fixture rows created by this module."""
    db.query(EntityGraphEdge).filter(
        EntityGraphEdge.predicate.in_(["_tarc_pred", "_tarc_pred2"])
    ).delete(synchronize_session=False)
    db.query(Court).filter(Court.courtlistener_id.like("_tarc_%")).delete(
        synchronize_session=False
    )
    db.query(Location).filter(Location.name.like("_tarc_%")).delete(
        synchronize_session=False
    )
    db.commit()


class TestMapRelationshipArcs:
    """Integration tests for the /api/map/relationship-arcs endpoint."""

    def test_arc_endpoint_returns_feature_collection_shape(self) -> None:
        """GET /api/map/relationship-arcs returns valid GeoJSON FeatureCollection shape."""
        response = client.get("/api/map/relationship-arcs")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["features"], list)
        assert "returned_count" in data
        assert data["returned_count"] == len(data["features"])
        assert "disclaimer" in data
        assert "arcs_enabled" in data

    def test_arc_court_to_court_renders_linestring(self) -> None:
        """Court-to-court active edge is returned as a LineString with correct GeoJSON coords.

        The settings override enables arcs with min_evidence=0 so the fixture edge
        (which carries two evidence refs) passes the publication policy gate.
        """
        with SessionLocal() as db:
            _arc_cleanup(db)

            loc1 = Location(
                name="_tarc_loc1",
                latitude=45.5,
                longitude=-73.6,
                location_type="courthouse",
            )
            loc2 = Location(
                name="_tarc_loc2",
                latitude=49.2,
                longitude=-123.1,
                location_type="courthouse",
            )
            db.add_all([loc1, loc2])
            db.flush()

            court1 = Court(
                courtlistener_id="_tarc_c1",
                name="_tarc_Court1",
                location_id=loc1.id,
            )
            court2 = Court(
                courtlistener_id="_tarc_c2",
                name="_tarc_Court2",
                location_id=loc2.id,
            )
            db.add_all([court1, court2])
            db.flush()

            edge = EntityGraphEdge(
                subject_type="court",
                subject_id=court1.id,
                predicate="_tarc_pred",
                object_type="court",
                object_id=court2.id,
                status="active",
                created_by="test",
                valid_from=datetime.now(timezone.utc),
                # Two evidence refs so this edge passes the min-evidence gate
                evidence_refs=[
                    {"evidence_id": 1, "confidence": 0.95},
                    {"evidence_id": 2, "confidence": 0.90},
                ],
            )
            db.add(edge)
            db.flush()

            # Save values before session closes
            edge_id = edge.id
            c1_id = court1.id
            c2_id = court2.id
            lon1, lat1 = loc1.longitude, loc1.latitude
            lon2, lat2 = loc2.longitude, loc2.latitude
            db.commit()

        with _arcs_enabled_override(min_evidence=2):
            response = client.get("/api/map/relationship-arcs")
        assert response.status_code == 200
        data = response.json()
        assert data["arcs_enabled"] is True
        features = data["features"]

        matching = [f for f in features if f["properties"]["edge_id"] == edge_id]
        assert len(matching) == 1, "Expected exactly one feature for our fixture edge"
        feature = matching[0]

        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "LineString"
        coords = feature["geometry"]["coordinates"]
        assert len(coords) == 2
        assert coords[0] == pytest.approx([lon1, lat1])
        assert coords[1] == pytest.approx([lon2, lat2])

        props = feature["properties"]
        assert props["predicate"] == "_tarc_pred"
        assert props["subject_type"] == "court"
        assert props["subject_id"] == c1_id
        assert props["object_type"] == "court"
        assert props["object_id"] == c2_id

        with SessionLocal() as db:
            _arc_cleanup(db)

    def test_arc_inactive_edge_excluded(self) -> None:
        """Edges with status != 'active' are excluded from the response."""
        with SessionLocal() as db:
            _arc_cleanup(db)

            loc1 = Location(
                name="_tarc_loc_r1",
                latitude=43.7,
                longitude=-79.4,
                location_type="courthouse",
            )
            loc2 = Location(
                name="_tarc_loc_r2",
                latitude=51.0,
                longitude=-114.1,
                location_type="courthouse",
            )
            db.add_all([loc1, loc2])
            db.flush()

            court1 = Court(
                courtlistener_id="_tarc_cr1",
                name="_tarc_CourtR1",
                location_id=loc1.id,
            )
            court2 = Court(
                courtlistener_id="_tarc_cr2",
                name="_tarc_CourtR2",
                location_id=loc2.id,
            )
            db.add_all([court1, court2])
            db.flush()

            retracted = EntityGraphEdge(
                subject_type="court",
                subject_id=court1.id,
                predicate="_tarc_pred2",
                object_type="court",
                object_id=court2.id,
                status="retracted",
                created_by="test",
                valid_from=datetime.now(timezone.utc),
            )
            db.add(retracted)
            db.flush()
            retracted_id = retracted.id
            db.commit()

        response = client.get("/api/map/relationship-arcs")
        assert response.status_code == 200
        features = response.json()["features"]
        ids_in_response = {f["properties"]["edge_id"] for f in features}
        assert retracted_id not in ids_in_response, (
            "Retracted edge must not appear in relationship-arcs response"
        )

        with SessionLocal() as db:
            _arc_cleanup(db)
