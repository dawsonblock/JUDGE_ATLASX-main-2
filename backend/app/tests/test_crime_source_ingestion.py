from datetime import datetime, timezone
from io import StringIO

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.ingestion.crime_sources.base import CrimeIncidentRecord
from app.ingestion.crime_sources.manual_csv import import_crime_incidents_csv
from app.ingestion.crime_sources.persistence import CrimeIncidentValidationError, persist_crime_incident
from app.models.entities import CrimeIncident


def crime_record(**overrides) -> CrimeIncidentRecord:
    values = {
        "source_id": "TEST-SOURCE",
        "external_id": "TEST-001",
        "incident_type": "Assault",
        "incident_category": "violent",
        "reported_at": datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
        "occurred_at": datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc),
        "city": "Test City",
        "province_state": "TC",
        "country": "Canada",
        "public_area_label": "Central district",
        "latitude_public": 52.1,
        "longitude_public": -106.6,
        "precision_level": "general_area",
        "source_url": "https://example.test/source",
        "source_name": "TEST Police Open Data",
        "verification_status": "reported",
        "data_last_seen_at": datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc),
        "is_public": False,
        "notes": "Generalized public-area record.",
    }
    values.update(overrides)
    return CrimeIncidentRecord(**values)


def test_crime_incident_record_persists():
    with SessionLocal() as db:
        incident = persist_crime_incident(db, crime_record(external_id="PERSIST-001"))
        db.commit()
        assert incident.id is not None
        assert incident.incident_category == "violent"
        assert incident.precision_level == "general_area"


def test_duplicate_source_and_external_id_updates_existing_record():
    with SessionLocal() as db:
        first = persist_crime_incident(db, crime_record(external_id="DUP-001", incident_type="Assault"))
        db.commit()
        first_id = first.id
        second = persist_crime_incident(db, crime_record(external_id="DUP-001", incident_type="Robbery"))
        db.commit()
        count = db.scalar(select(func.count()).select_from(CrimeIncident).where(CrimeIncident.source_name == "TEST Police Open Data", CrimeIncident.external_id == "DUP-001"))
        assert second.id == first_id
        assert second.incident_type == "Robbery"
        assert count == 1


def test_missing_external_id_uses_stable_derived_id():
    with SessionLocal() as db:
        first = persist_crime_incident(db, crime_record(external_id=None, incident_type="Theft"))
        db.commit()
        first_external_id = first.external_id
        second = persist_crime_incident(db, crime_record(external_id=None, incident_type="Theft"))
        db.commit()
        assert first_external_id is not None
        assert first_external_id.startswith("DERIVED-")
        assert second.id == first.id
        assert second.external_id == first_external_id


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("latitude_public", 0.0, "zero_public_coordinates"),
        ("longitude_public", 0.0, "zero_public_coordinates"),
        ("precision_level", "exact_address", "exact_address_precision_rejected"),
        ("notes", "Contains suspect home details.", "unsafe_private_or_person_specific_notes"),
    ],
)
def test_unsafe_crime_incident_records_are_rejected(field, value, reason):
    with SessionLocal() as db:
        with pytest.raises(CrimeIncidentValidationError, match=reason):
            persist_crime_incident(db, crime_record(external_id=f"REJECT-{field}", **{field: value}))


def test_manual_csv_import_returns_counters():
    csv_data = StringIO(
        "\n".join(
            [
                "source_id,external_id,incident_type,incident_category,reported_at,occurred_at,city,province_state,country,public_area_label,latitude_public,longitude_public,precision_level,source_url,source_name,verification_status,notes",
                "CSV,CSV-001,Assault,Violent,2026-04-25T12:00:00Z,2026-04-25T08:00:00Z,Saskatoon,SK,Canada,Downtown,52.13,-106.67,general_area,https://example.test,SAMPLE CSV Source,reported,Generalized record",
                "CSV,CSV-002,Theft,Property,2026-04-25T12:00:00Z,2026-04-25T08:00:00Z,Saskatoon,SK,Canada,Downtown,0.0,-106.67,general_area,https://example.test,SAMPLE CSV Source,reported,Generalized record",
                "CSV,CSV-003,Robbery,Violent,not-a-date,2026-04-25T08:00:00Z,Saskatoon,SK,Canada,Downtown,52.13,-106.67,general_area,https://example.test,SAMPLE CSV Source,reported,Generalized record",
            ]
        )
    )
    with SessionLocal() as db:
        result = import_crime_incidents_csv(db, csv_data)
        assert result.read_count == 3
        assert result.persisted_count == 1
        assert result.skipped_count == 1
        assert result.error_count == 1
        assert any("zero_public_coordinates" in error for error in result.errors)
        assert any("not-a-date" in error for error in result.errors)


def test_admin_crime_import_route_is_disabled_by_default(client):
    response = client.post("/api/admin/import/crime-incidents/manual-csv")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Phase 6: CSV import safety tests
# ---------------------------------------------------------------------------

def test_csv_import_defaults_is_public_false():
    csv_data = StringIO(
        "\n".join([
            "source_id,external_id,incident_type,incident_category,reported_at,occurred_at,city,province_state,country,public_area_label,latitude_public,longitude_public,precision_level,source_url,source_name,verification_status,notes",
            "CSV,CSV-PUB-001,Assault,Violent,2026-04-25T12:00:00Z,2026-04-25T08:00:00Z,Saskatoon,SK,Canada,Downtown,52.13,-106.67,general_area,https://example.test,SAMPLE CSV PUB Source,reported,Generalized",
        ])
    )
    with SessionLocal() as db:
        result = import_crime_incidents_csv(db, csv_data)
        assert result.persisted_count == 1
        incident = db.query(CrimeIncident).filter_by(external_id="CSV-PUB-001").one()
        assert incident.is_public is False, "CSV import must default is_public=False (privacy-by-default)"
        assert incident.review_status == "pending_review"


def test_csv_import_invalid_source_url_is_skipped():
    csv_data = StringIO(
        "\n".join([
            "source_id,external_id,incident_type,incident_category,reported_at,occurred_at,city,province_state,country,public_area_label,latitude_public,longitude_public,precision_level,source_url,source_name,verification_status,notes",
            "CSV,CSV-URL-001,Assault,Violent,2026-04-25T12:00:00Z,2026-04-25T08:00:00Z,Saskatoon,SK,Canada,Downtown,52.13,-106.67,general_area,not-a-url,SAMPLE CSV URL Source,reported,Generalized",
        ])
    )
    with SessionLocal() as db:
        result = import_crime_incidents_csv(db, csv_data)
    assert result.persisted_count == 0
    assert result.skipped_count + result.error_count >= 1


def test_tier_hold_source_unconditionally_revokes_approval_on_reingest():
    """Phase 2 hold enforcement: TIER_HOLD sources (including unknown sources that
    fail-closed) must always demote review_status back to pending_review on re-ingest,
    regardless of whether only non-safety fields changed.

    'TEST Police Open Data' is not in _SOURCE_TIER_MAP so source_tier() returns
    TIER_HOLD, and resolve_publication_policy returns TIER_HOLD (fail-closed).
    The Phase 2 unconditional block then demotes any previously-approved status.
    """
    with SessionLocal() as db:
        first = persist_crime_incident(db, crime_record(
            external_id="APPROVED-001",
            incident_type="Assault",
        ))
        db.commit()
        first.review_status = "official_police_open_data_report"  # manually approved
        db.commit()
        first_id = first.id

        second = persist_crime_incident(db, crime_record(
            external_id="APPROVED-001",
            incident_type="Assault",
            verification_status="corroborated",
        ))
        db.commit()
        second_id = second.id
        second_review_status = second.review_status

    assert second_id == first_id
    assert second_review_status == "pending_review", (
        "TIER_HOLD source must unconditionally demote review_status to pending_review on re-ingest (Phase 2)"
    )


# ---------------------------------------------------------------------------
# P2: ORM-level default tests
# ---------------------------------------------------------------------------

def test_crime_incident_orm_defaults_is_public_false():
    incident = CrimeIncident(
        incident_type="Assault",
        incident_category="violent",
        source_name="test",
        precision_level="general_area",
        verification_status="reported",
        review_status="pending_review",
    )
    assert incident.is_public is not True, (
        "CrimeIncident ORM default must never be True before flush "
        "(privacy-by-default; column default=False applied at INSERT time)"
    )


def test_crime_incident_orm_defaults_review_status_pending():
    incident = CrimeIncident(
        incident_type="Assault",
        incident_category="violent",
        source_name="test",
        precision_level="general_area",
        verification_status="reported",
    )
    assert incident.review_status in (None, "pending_review"), (
        "CrimeIncident review_status must default to pending_review or be unset before flush"
    )
