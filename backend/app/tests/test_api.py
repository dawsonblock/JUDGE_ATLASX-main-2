from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.db.session import SessionLocal
from app.api.routes import _is_mappable
from app.ingestion.adapters import ParsedRecord
from app.ingestion.persistence import persist_parsed_record
from app.models.entities import (
    Case,
    CaseParty,
    Court,
    CrimeIncident,
    Event,
    EventDefendant,
    EventSource,
    EvidenceReview,
    LegalSource,
    Location,
)
from app.seed.sample_data import verify_seed_correctness
from app.services.constants import OUTCOME_UNKNOWN
from app.services.linker import url_hash
from app.services.text import normalize_docket


def _add_public_event_source(db, event: Event, key: str) -> None:
    url = f"https://example.test/{key}"
    source = LegalSource(
        source_id=f"SRC-{key.upper()}",
        source_type="court_record",
        title=f"Source for {key}",
        url=url,
        url_hash=url_hash(url),
        source_quality="court_record",
        verified_flag=True,
        review_status="verified_court_record",
        public_visibility=True,
    )
    db.add(source)
    db.flush()
    db.add(EventSource(event_id=event.id, source_id=source.id))


def test_geojson_endpoint_returns_feature_collection(client):
    response = client.get("/api/map/events")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) >= 7
    for feature in payload["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        longitude, latitude = feature["geometry"]["coordinates"]
        assert isinstance(longitude, (float, int))
        assert isinstance(latitude, (float, int))
        assert -180 <= longitude <= 180
        assert -90 <= latitude <= 90


def test_geojson_endpoint_includes_map_properties_without_public_names(client):
    response = client.get("/api/map/events")
    assert response.status_code == 200
    feature = response.json()["features"][0]
    properties = feature["properties"]
    for key in [
        "event_id",
        "judge_id",
        "judge_name",
        "court_id",
        "court_name",
        "location_id",
        "location_name",
        "event_type",
        "event_date",
        "case_id",
        "case_name",
        "case_number",
        "verified_flag",
        "repeat_offender_indicator",
        "location_status",
        "is_mappable",
    ]:
        assert key in properties
    assert properties["is_mappable"] is True
    assert properties["location_status"] == "mapped"
    assert properties["defendants"]
    assert all(label.startswith("DEF-") for label in properties["defendants"])
    serialized = str(response.json())
    assert "public_name" not in serialized
    assert "SAMPLE Defendant Alpha" not in serialized


def test_outcome_unknown_fallback(client):
    response = client.get("/api/events/EVT-SAMPLE-001")
    assert response.status_code == 200
    assert response.json()["outcome_status"] == OUTCOME_UNKNOWN


def test_defendant_names_anonymized_by_default(client):
    response = client.get("/api/events/EVT-SAMPLE-001")
    assert response.status_code == 200
    defendant = response.json()["defendants"][0]
    assert defendant["display_label"].startswith("DEF-")
    assert "public_name" not in defendant


def test_events_filters_match_map_filters(client):
    events_response = client.get("/api/events?event_type=revocation")
    map_response = client.get("/api/map/events?event_type=revocation")
    assert events_response.status_code == 200
    assert map_response.status_code == 200
    events = events_response.json()
    features = map_response.json()["features"]
    assert len(events) == len(features)
    assert {event["event_id"] for event in events} == {
        feature["properties"]["event_id"] for feature in features
    }


def test_post_event_requires_admin_auth_before_validation(client):
    response = client.post(
        "/api/events",
        json={
            "court_id": 999999,
            "case_id": 1,
            "primary_location_id": 1,
            "event_type": "sentencing",
            "title": "Invalid court",
            "summary": "Should fail cleanly.",
        },
    )
    assert response.status_code == 403


def test_invalid_post_event_foreign_keys_return_422_with_admin_token(
    client, monkeypatch
):
    class EnabledSettings:
        enable_admin_imports = True
        enable_admin_review = False
        enable_public_event_post = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    response = client.post(
        "/api/events",
        headers={"X-JTA-Admin-Token": "test-token"},
        json={
            "court_id": 999999,
            "case_id": 1,
            "primary_location_id": 1,
            "event_type": "sentencing",
            "title": "Invalid court",
            "summary": "Should fail cleanly.",
        },
    )
    assert response.status_code == 422
    assert "court_id" in response.json()["detail"]


def test_repeat_offender_keyword_is_exposed_as_indicator(client):
    response = client.get("/api/events/EVT-SAMPLE-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["repeat_offender_indicator"] is True
    assert "repeat_offender_flag" not in payload
    assert "repeat_offender_indicator_flag" not in payload
    assert payload["verification_status"] == "indicator_only"


def test_unknown_court_event_appears_in_events_but_not_map(client):
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="unknown-court-1",
        docket_number="9:25-cr-404",
        court_code="unknown_test_court",
        caption="United States v. Unknown Court Sample",
        docket_text="Judgment as to unknown court sample. Sentenced to a sample term.",
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/unknown-court-1/",
        source_public_url="https://www.courtlistener.com/recap/unknown-court-1/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        event = db.scalar(db.query(Event).filter_by(event_id=result.event_id).statement)
        event.review_status = "verified_court_record"
        event.public_visibility = True
        for link in event.source_links:
            link.source.review_status = "verified_court_record"
            link.source.public_visibility = True
        db.commit()
        event_id = result.event_id

    events_response = client.get("/api/events?event_type=sentencing&limit=500")
    map_response = client.get("/api/map/events?event_type=sentencing&limit=500")
    assert events_response.status_code == 200
    assert map_response.status_code == 200

    events = events_response.json()
    features = map_response.json()["features"]
    unknown_event = next(event for event in events if event["event_id"] == event_id)
    assert unknown_event["is_mappable"] is False
    assert unknown_event["location_status"] == "court_location_pending"
    assert event_id not in {feature["properties"]["event_id"] for feature in features}


def test_placeholder_location_with_coordinates_never_maps(client):
    with SessionLocal() as db:
        location = Location(
            name="Placeholder with coordinates",
            location_type="court_placeholder",
            city="Sample City",
            state="SC",
            region="Sample",
            latitude=41.0,
            longitude=-87.0,
        )
        db.add(location)
        db.flush()
        court = Court(
            courtlistener_id="placeholder_coords",
            name="Placeholder Coordinate Court",
            jurisdiction="Federal",
            region="Sample",
            location_id=location.id,
        )
        db.add(court)
        db.flush()
        case = Case(
            court_id=court.id,
            docket_number="1:25-cr-placeholder",
            normalized_docket_number=normalize_docket("1:25-cr-placeholder"),
            caption="United States v. Placeholder Coordinates",
            case_type="criminal",
        )
        db.add(case)
        db.flush()
        event = Event(
            event_id="EVT-PLACEHOLDER-COORDS",
            court_id=court.id,
            case_id=case.id,
            primary_location_id=location.id,
            event_type="sentencing",
            title="Placeholder coordinate event",
            summary="This event should not map because the location is a placeholder.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            review_status="verified_court_record",
            public_visibility=True,
        )
        db.add(event)
        db.flush()
        _add_public_event_source(db, event, "placeholder-coords")
        db.commit()

    events_response = client.get("/api/events?event_type=sentencing&limit=500")
    map_response = client.get("/api/map/events?event_type=sentencing&limit=500")
    events = events_response.json()
    features = map_response.json()["features"]
    placeholder_event = next(
        event for event in events if event["event_id"] == "EVT-PLACEHOLDER-COORDS"
    )
    assert placeholder_event["is_mappable"] is False
    assert placeholder_event["location_status"] == "court_location_pending"
    assert "EVT-PLACEHOLDER-COORDS" not in {
        feature["properties"]["event_id"] for feature in features
    }
    assert any(
        feature["properties"]["event_id"] == "EVT-SAMPLE-003" for feature in features
    )


def test_zero_coordinate_courthouse_event_is_listed_but_not_mapped(client):
    with SessionLocal() as db:
        location = Location(
            name="Zero coordinate courthouse",
            location_type="courthouse",
            city="Sample City",
            state="SC",
            region="Sample",
            latitude=0.0,
            longitude=-91.0,
        )
        db.add(location)
        db.flush()
        court = Court(
            courtlistener_id="zero_coords",
            name="Zero Coordinate Court",
            jurisdiction="Federal",
            region="Sample",
            location_id=location.id,
        )
        db.add(court)
        db.flush()
        case = Case(
            court_id=court.id,
            docket_number="1:25-cr-zero",
            normalized_docket_number=normalize_docket("1:25-cr-zero"),
            caption="United States v. Zero Coordinates",
            case_type="criminal",
        )
        db.add(case)
        db.flush()
        event = Event(
            event_id="EVT-ZERO-COORDS",
            court_id=court.id,
            case_id=case.id,
            primary_location_id=location.id,
            event_type="sentencing",
            title="Zero coordinate event",
            summary="This event should not map because the latitude is zero.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            review_status="verified_court_record",
            public_visibility=True,
        )
        db.add(event)
        db.flush()
        _add_public_event_source(db, event, "zero-coords")
        db.commit()

    events_response = client.get("/api/events?event_type=sentencing&limit=500")
    map_response = client.get("/api/map/events?event_type=sentencing&limit=500")
    events = events_response.json()
    features = map_response.json()["features"]
    zero_event = next(
        event for event in events if event["event_id"] == "EVT-ZERO-COORDS"
    )
    assert zero_event["is_mappable"] is False
    assert zero_event["location_status"] == "court_location_pending"
    assert "EVT-ZERO-COORDS" not in {
        feature["properties"]["event_id"] for feature in features
    }


def test_mappability_helper_rejects_missing_coordinates():
    location = Location(
        name="Missing coordinates",
        location_type="courthouse",
        latitude=10.0,
        longitude=10.0,
    )
    location.latitude = None
    assert _is_mappable(None) is False
    assert _is_mappable(location) is False


def test_crime_incidents_endpoint_returns_safe_feature_collection(client):
    response = client.get("/api/map/crime-incidents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) >= 4
    for feature in payload["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        longitude, latitude = feature["geometry"]["coordinates"]
        assert isinstance(longitude, (float, int))
        assert isinstance(latitude, (float, int))
        properties = feature["properties"]
        for key in [
            "incident_id",
            "incident_type",
            "incident_category",
            "reported_at",
            "city",
            "area_label",
            "precision_level",
            "source_name",
            "verification_status",
            "disclaimer",
        ]:
            assert key in properties
        assert "not proof of guilt or conviction" in properties["disclaimer"]
    serialized = str(payload).lower()
    assert "public_name" not in serialized
    assert "victim" not in serialized
    assert "suspect" not in serialized
    assert "address" not in serialized
    assert "dob" not in serialized
    assert "family" not in serialized
    assert "residence" not in serialized
    assert "home" not in serialized


def test_crime_incidents_filters(client):
    city_response = client.get("/api/map/crime-incidents?city=Saskatoon")
    category_response = client.get(
        "/api/map/crime-incidents?incident_category=property"
    )
    source_response = client.get(
        "/api/map/crime-incidents?source_name=SAMPLE%20Chicago%20Data%20Portal"
    )
    start = (
        (datetime.now(timezone.utc) - timedelta(days=2))
        .isoformat()
        .replace("+00:00", "Z")
    )
    end = (
        (datetime.now(timezone.utc) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    date_response = client.get(f"/api/map/crime-incidents?start={start}&end={end}")
    status_response = client.get(
        "/api/map/crime-incidents?verification_status=reported"
    )

    assert {
        feature["properties"]["city"] for feature in city_response.json()["features"]
    } == {"Saskatoon"}
    assert {
        feature["properties"]["incident_category"]
        for feature in category_response.json()["features"]
    } == {"property"}
    assert {
        feature["properties"]["source_name"]
        for feature in source_response.json()["features"]
    } == {"SAMPLE Chicago Data Portal"}
    assert {
        feature["properties"]["verification_status"]
        for feature in status_response.json()["features"]
    } == {"reported"}
    assert {
        feature["properties"]["city"] for feature in date_response.json()["features"]
    } == {"Saskatoon", "Toronto"}


def test_crime_incidents_exclude_non_public_and_unmappable_records(client):
    with SessionLocal() as db:
        db.add_all(
            [
                CrimeIncident(
                    source_id="TEST",
                    external_id="PRIVATE",
                    incident_type="SAMPLE Private record",
                    incident_category="property",
                    city="Hidden City",
                    province_state="HC",
                    country="Canada",
                    public_area_label="Hidden",
                    latitude_public=51.0,
                    longitude_public=-101.0,
                    precision_level="general_area",
                    source_name="SAMPLE Hidden Source",
                    verification_status="reported",
                    is_public=False,
                ),
                CrimeIncident(
                    source_id="TEST",
                    external_id="ZERO",
                    incident_type="SAMPLE Zero record",
                    incident_category="property",
                    city="Zero City",
                    province_state="ZC",
                    country="Canada",
                    public_area_label="Zero",
                    latitude_public=0.0,
                    longitude_public=-101.0,
                    precision_level="general_area",
                    source_name="SAMPLE Zero Source",
                    verification_status="reported",
                    is_public=True,
                ),
                CrimeIncident(
                    source_id="TEST",
                    external_id="MISSING",
                    incident_type="SAMPLE Missing record",
                    incident_category="property",
                    city="Missing City",
                    province_state="MC",
                    country="Canada",
                    public_area_label="Missing",
                    latitude_public=None,
                    longitude_public=-101.0,
                    precision_level="general_area",
                    source_name="SAMPLE Missing Source",
                    verification_status="reported",
                    is_public=True,
                ),
            ]
        )
        db.commit()

    response = client.get(
        "/api/map/crime-incidents?incident_category=property&limit=2000"
    )
    cities = {feature["properties"]["city"] for feature in response.json()["features"]}
    assert "Hidden City" not in cities
    assert "Zero City" not in cities
    assert "Missing City" not in cities


def test_pending_rejected_removed_events_are_hidden_from_public_endpoints(client):
    with SessionLocal() as db:
        for index, status in enumerate(
            ["pending_review", "rejected", "removed_from_public"], start=1
        ):
            event = Event(
                event_id=f"EVT-HIDDEN-{index}",
                court_id=1,
                case_id=1,
                primary_location_id=1,
                event_type="sentencing",
                title=f"Hidden {status}",
                summary="Hidden review-status sample.",
                repeat_offender_indicator=False,
                verified_flag=True,
                source_quality="court_record",
                review_status=status,
                public_visibility=status == "pending_review",
            )
            db.add(event)
        db.commit()

    events_response = client.get("/api/events?event_type=sentencing&limit=500")
    map_response = client.get("/api/map/events?event_type=sentencing&limit=500")
    public_event_ids = {event["event_id"] for event in events_response.json()}
    public_map_ids = {
        feature["properties"]["event_id"] for feature in map_response.json()["features"]
    }
    assert not {"EVT-HIDDEN-1", "EVT-HIDDEN-2", "EVT-HIDDEN-3"} & public_event_ids
    assert not {"EVT-HIDDEN-1", "EVT-HIDDEN-2", "EVT-HIDDEN-3"} & public_map_ids


def test_corrected_event_remains_public_with_review_status(client):
    with SessionLocal() as db:
        event = Event(
            event_id="EVT-CORRECTED-PUBLIC",
            court_id=1,
            case_id=1,
            primary_location_id=1,
            event_type="sentencing",
            title="Corrected public event",
            summary="Corrected review-status sample.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            review_status="corrected",
            correction_note="SAMPLE correction note.",
            public_visibility=True,
        )
        db.add(event)
        db.flush()
        _add_public_event_source(db, event, "corrected-public")
        db.commit()

    events_response = client.get("/api/events?event_type=sentencing&limit=500")
    payload = next(
        event
        for event in events_response.json()
        if event["event_id"] == "EVT-CORRECTED-PUBLIC"
    )
    assert payload["review_status"] == "corrected"


def test_pending_crime_incident_is_hidden_from_public_map(client):
    with SessionLocal() as db:
        db.add(
            CrimeIncident(
                source_id="TEST",
                external_id="PENDING-CRIME",
                incident_type="SAMPLE Pending incident",
                incident_category="property",
                city="Pending City",
                province_state="PC",
                country="Canada",
                public_area_label="Pending area",
                latitude_public=51.0,
                longitude_public=-101.0,
                precision_level="general_area",
                source_name="SAMPLE Pending Source",
                verification_status="reported",
                is_public=True,
                review_status="pending_review",
            )
        )
        db.commit()

    response = client.get("/api/map/crime-incidents?limit=2000")
    assert "Pending City" not in {
        feature["properties"]["city"] for feature in response.json()["features"]
    }


def test_source_panel_returns_safe_event_source_metadata(client):
    response = client.get("/api/evidence/source-panel/event/EVT-SAMPLE-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_type"] == "event"
    assert payload["review_status"] == "verified_court_record"
    assert payload["sources"]
    source = payload["sources"][0]
    assert source["source_name"]
    assert source["source_type"]
    assert source["source_url"]
    serialized = str(payload).lower()
    for forbidden in [
        "public_name",
        "suspect",
        "victim",
        "address",
        "dob",
        "family",
        "residence",
        "home",
    ]:
        assert forbidden not in serialized
    assert "sample defendant alpha" not in serialized


def test_source_panel_returns_safe_crime_incident_metadata(client):
    map_response = client.get("/api/map/crime-incidents")
    incident_id = map_response.json()["features"][0]["properties"]["incident_id"]
    response = client.get(f"/api/evidence/source-panel/crime_incident/{incident_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_type"] == "crime_incident"
    assert payload["review_status"] == "official_police_open_data_report"
    assert payload["sources"]
    source = payload["sources"][0]
    assert source["trust_reason"].startswith("Official reported-incident source")
    serialized = str(payload).lower()
    for forbidden in [
        "public_name",
        "suspect",
        "victim",
        "address",
        "dob",
        "family",
        "residence",
        "home",
    ]:
        assert forbidden not in serialized


def test_public_endpoints_sanitize_case_source_summary_and_excerpt(client):
    with SessionLocal() as db:
        case = Case(
            court_id=1,
            docket_number="1:26-cr-private",
            normalized_docket_number=normalize_docket("1:26-cr-private"),
            caption="United States v. Sample Alpha",
            case_type="criminal",
        )
        db.add(case)
        db.flush()
        db.add(
            CaseParty(
                case_id=case.id,
                defendant_id=1,
                party_type="defendant",
                public_name="Sample Alpha",
                normalized_name="sample alpha",
            )
        )
        source = LegalSource(
            source_id="SRC-PRIVACY-REGRESSION",
            source_type="court_record",
            title="Court order for Sample Alpha",
            url="https://example.test/privacy-regression",
            url_hash=url_hash("https://example.test/privacy-regression"),
            source_quality="court_record",
            verified_flag=True,
            review_status="verified_court_record",
            public_visibility=True,
        )
        db.add(source)
        db.flush()
        event = Event(
            event_id="EVT-PRIVACY-REGRESSION",
            court_id=1,
            judge_id=1,
            case_id=case.id,
            primary_location_id=1,
            event_type="sentencing",
            title="Sentencing order for Sample Alpha",
            summary="Sample Alpha DOB: 01/02/1990. The home address is 123 Main Street.",
            repeat_offender_indicator=True,
            verified_flag=True,
            source_quality="court_record",
            classifier_metadata={
                "source_excerpt": "Sample Alpha DOB: 01/02/1990. The home address is 123 Main Street.",
                "verification_status": "indicator_only",
                "repeat_offender_indicators": ["criminal history"],
            },
            review_status="verified_court_record",
            public_visibility=True,
        )
        db.add(event)
        db.flush()
        db.add(EventDefendant(event_id=event.id, defendant_id=1))
        db.add(EventSource(event_id=event.id, source_id=source.id))
        db.commit()
        case_id = case.id

    responses = [
        client.get("/api/events/EVT-PRIVACY-REGRESSION"),
        client.get("/api/map/events?event_type=sentencing&limit=2000"),
        client.get(f"/api/cases/{case_id}"),
        client.get("/api/sources"),
        client.get("/api/sources/SRC-PRIVACY-REGRESSION"),
        client.get("/api/evidence/source-panel/event/EVT-PRIVACY-REGRESSION"),
    ]
    for response in responses:
        assert response.status_code == 200
        serialized = str(response.json()).lower()
        for forbidden in [
            "sample alpha",
            "123 main street",
            "01/02/1990",
            "dob",
            "address",
            "home",
        ]:
            assert forbidden not in serialized
    event_payload = responses[0].json()
    assert event_payload["repeat_offender_indicator"] is True
    assert "repeat_offender_flag" not in event_payload
    assert "repeat_offender_indicator_flag" not in event_payload


def test_admin_review_routes_return_403_when_disabled(client):
    queue_response = client.get("/api/admin/review-queue")
    decision_response = client.post(
        "/api/admin/review-queue/event/EVT-SAMPLE-001/decision",
        json={"decision": "dispute"},
    )
    assert queue_response.status_code == 403
    assert decision_response.status_code == 403


def test_admin_routes_require_token_when_enabled(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = True
        enable_admin_review = True
        enable_public_event_post = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    protected_requests = [
        (
            "post",
            "/api/events",
            {
                "json": {
                    "court_id": 999999,
                    "case_id": 1,
                    "primary_location_id": 1,
                    "event_type": "sentencing",
                    "title": "Invalid",
                    "summary": "Invalid",
                }
            },
        ),
        ("post", "/api/ingest/courtlistener?since=2026-01-01T00:00:00Z", {}),
        ("post", "/api/admin/import/crime-incidents/manual-csv", {}),
        ("post", "/api/admin/ai/process-source/SRC-SAMPLE-001", {}),
        ("get", "/api/admin/review/items", {}),
        ("post", "/api/admin/review/items/1/approve", {"json": {"actor": "admin"}}),
        ("get", "/api/admin/review-queue", {}),
        ("get", "/api/evidence/entity/event/1", {}),
        ("get", "/api/evidence/relationship/event/1/person/1", {}),
        (
            "post",
            "/api/admin/review-queue/event/EVT-SAMPLE-001/decision",
            {"json": {"decision": "dispute"}},
        ),
    ]
    for method, path, kwargs in protected_requests:
        missing = getattr(client, method)(path, **kwargs)
        wrong = getattr(client, method)(
            path, headers={"X-JTA-Admin-Token": "wrong-token"}, **kwargs
        )
        assert missing.status_code == 403
        assert wrong.status_code == 403


def test_admin_routes_accept_valid_token_and_use_pagination(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = True
        enable_admin_review = True
        enable_public_event_post = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth
    import app.api.routes.ingestion as ingestion_routes

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    monkeypatch.setattr(
        ingestion_routes,
        "run_courtlistener_ingestion",
        lambda db, since, commit=True: SimpleNamespace(
            id=1,
            status="completed",
            fetched_count=0,
            parsed_count=0,
            persisted_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
        ),
    )
    headers = {"X-JTA-Admin-Token": "test-token"}

    queue_response = client.get(
        "/api/admin/review-queue?limit=2&offset=1", headers=headers
    )
    review_items_response = client.get(
        "/api/admin/review/items?limit=2&offset=0", headers=headers
    )
    csv_response = client.post(
        "/api/admin/import/crime-incidents/manual-csv", headers=headers
    )
    ingest_response = client.post(
        "/api/ingest/courtlistener?since=2026-01-01T00:00:00Z", headers=headers
    )
    ai_response = client.post(
        "/api/admin/ai/process-source/SRC-SAMPLE-001", headers=headers
    )
    entity_evidence_response = client.get(
        "/api/evidence/entity/event/1", headers=headers
    )
    relationship_evidence_response = client.get(
        "/api/evidence/relationship/event/1/person/1", headers=headers
    )

    assert queue_response.status_code == 200
    assert len(queue_response.json()["items"]) <= 2
    assert queue_response.json()["total_count"] >= len(queue_response.json()["items"])
    assert review_items_response.status_code == 200
    assert len(review_items_response.json()["items"]) <= 2
    assert csv_response.status_code == 422
    assert ingest_response.status_code == 200
    assert ai_response.status_code == 200
    assert entity_evidence_response.status_code == 200
    assert relationship_evidence_response.status_code == 200


def test_admin_review_decision_updates_entity_and_audit(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = True
        enable_admin_review = True
        jwt_auth_enabled = True
        enable_legacy_admin_token = False
        enforce_jwt_mutations = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth
    from app.auth.jwt_handler import create_access_token

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    reviewer_token = create_access_token(email="reviewer@example.test", role="reviewer")
    response = client.post(
        "/api/admin/review-queue/event/EVT-SAMPLE-002/decision",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={
            "decision": "dispute",
            "reviewed_by": "reviewer@example.test",
            "notes": "Source needs follow-up.",
        },
    )
    assert response.status_code == 200
    assert response.json()["review_status"] == "disputed"
    assert response.json()["public_visibility"] is False
    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id="EVT-SAMPLE-002").one()
        audit = (
            db.query(EvidenceReview)
            .filter_by(entity_type="event", entity_id=event.id, new_status="disputed")
            .one()
        )
        assert event.review_status == "disputed"
        assert event.reviewed_by == "reviewer@example.test"
        assert audit.public_visibility is False


def test_ai_process_source_route_disabled_by_default(client):
    response = client.post("/api/admin/ai/process-source/SRC-SAMPLE-001")
    assert response.status_code == 403


def test_persisted_docket_text_defendant_name_redacted_in_public_event(client):
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="docket-text-name-test",
        docket_number="1:25-cr-nametest",
        court_code="nysd",
        caption="United States v. Real Sample Person",
        docket_text="Judgment as to Real Sample Person. Sentenced to a sample term.",
        parties=[{"party_type": "defendant", "name": "Real Sample Person"}],
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/nametest/",
        source_public_url="https://www.courtlistener.com/recap/nametest/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        event_obj = db.scalar(select(Event).where(Event.event_id == result.event_id))
        event_obj.review_status = "verified_court_record"
        event_obj.public_visibility = True
        for link in event_obj.source_links:
            link.source.review_status = "verified_court_record"
            link.source.public_visibility = True
        db.commit()
        event_id = result.event_id

    response = client.get(f"/api/events/{event_id}")
    assert response.status_code == 200
    payload = response.json()
    serialized = str(payload).lower()
    assert "real sample person" not in serialized
    assert "public_name" not in serialized


def test_seed_allows_post_seed_inserts_without_duplicate_key(client):
    with SessionLocal() as db:
        result = verify_seed_correctness(db)
        assert result is True


# ---------------------------------------------------------------------------
# Phase 5: map envelope + bbox + review-gate tests
# ---------------------------------------------------------------------------


def test_map_events_response_has_envelope_keys(client):
    response = client.get("/api/map/events")
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "type",
        "features",
        "returned_count",
        "truncated",
        "filters_applied",
        "disclaimer",
    ):
        assert key in payload, f"Missing envelope key: {key}"
    assert payload["type"] == "FeatureCollection"
    assert isinstance(payload["returned_count"], int)
    assert isinstance(payload["truncated"], bool)
    assert "public_visibility" in payload["filters_applied"]
    assert "review_status" in payload["filters_applied"]
    assert isinstance(payload["disclaimer"], str)
    assert len(payload["disclaimer"]) > 20


def test_map_events_bbox_north_american_returns_results(client):
    response = client.get("/api/map/events?bbox=-140,25,-60,70")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["returned_count"] >= 1
    assert "bbox" in payload["filters_applied"]


def test_map_events_bbox_empty_region_returns_zero(client):
    response = client.get("/api/map/events?bbox=0,0,1,1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["returned_count"] == 0
    assert payload["features"] == []


def test_map_events_bbox_invalid_format_returns_422(client):
    assert client.get("/api/map/events?bbox=1,2,3").status_code == 422
    assert client.get("/api/map/events?bbox=abc,1,2,3").status_code == 422
    assert client.get("/api/map/events?bbox=0,91,1,92").status_code == 422
    assert client.get("/api/map/events?bbox=0,10,1,5").status_code == 422


def test_map_events_review_gate_pending_not_visible(client):
    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        original_review = event.review_status
        original_visibility = event.public_visibility
        event.review_status = "pending_review"
        event.public_visibility = False
        db.commit()

    try:
        response = client.get("/api/map/events")
        event_ids = {f["properties"]["event_id"] for f in response.json()["features"]}
        assert (
            "EVT-SAMPLE-001" not in event_ids
        ), "pending_review event must not appear on public map"
    finally:
        with SessionLocal() as db:
            event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
            event.review_status = original_review
            event.public_visibility = original_visibility
            db.commit()


def test_map_events_returned_count_matches_features_length(client):
    response = client.get("/api/map/events")
    payload = response.json()
    assert payload["returned_count"] == len(payload["features"])


# ---------------------------------------------------------------------------
# P3: disputed records are hidden from public API
# ---------------------------------------------------------------------------


def test_disputed_event_hidden_from_map_and_events(client):
    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        original_review = event.review_status
        original_visibility = event.public_visibility
        event.review_status = "disputed"
        event.public_visibility = False
        db.commit()

    try:
        map_response = client.get("/api/map/events")
        event_ids_on_map = {
            f["properties"]["event_id"] for f in map_response.json()["features"]
        }
        assert (
            "EVT-SAMPLE-001" not in event_ids_on_map
        ), "disputed event must not appear on public map"

        list_response = client.get("/api/events")
        event_ids_in_list = {e["event_id"] for e in list_response.json()}
        assert (
            "EVT-SAMPLE-001" not in event_ids_in_list
        ), "disputed event must not appear in public events list"
    finally:
        with SessionLocal() as db:
            event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
            event.review_status = original_review
            event.public_visibility = original_visibility
            db.commit()


# ---------------------------------------------------------------------------
# Map record detail endpoint  (/api/map/record/{record_type}/{record_id})
# ---------------------------------------------------------------------------


def test_map_record_court_event_approved_returns_bundle(client):
    response = client.get("/api/map/record/court_event/EVT-SAMPLE-001")
    assert response.status_code == 200
    data = response.json()
    assert data["record_type"] == "court_event"
    assert data["id"] == "EVT-SAMPLE-001"
    assert "source_links" in data
    assert "news_articles" in data
    assert "related_reported_incidents" in data
    assert "audit" in data
    assert "disclaimer" in data
    assert data["disclaimer"] != ""
    assert "review_status" in data["audit"]


def test_map_record_court_event_pending_returns_404(client):
    with SessionLocal() as db:
        evt = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        orig_review_p, orig_vis_p = evt.review_status, evt.public_visibility
        evt.review_status = "pending_review"
        evt.public_visibility = False
        db.commit()
    try:
        assert (
            client.get("/api/map/record/court_event/EVT-SAMPLE-001").status_code == 404
        )
    finally:
        with SessionLocal() as db:
            evt2 = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
            evt2.review_status = orig_review_p
            evt2.public_visibility = orig_vis_p
            db.commit()


def test_map_record_court_event_disputed_returns_404(client):
    with SessionLocal() as db:
        evt = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        orig_review_d, orig_vis_d = evt.review_status, evt.public_visibility
        evt.review_status = "disputed"
        evt.public_visibility = False
        db.commit()
    try:
        assert (
            client.get("/api/map/record/court_event/EVT-SAMPLE-001").status_code == 404
        )
    finally:
        with SessionLocal() as db:
            evt2 = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
            evt2.review_status = orig_review_d
            evt2.public_visibility = orig_vis_d
            db.commit()


def _seed_incident_id() -> int:
    with SessionLocal() as db:
        return db.query(CrimeIncident).filter_by(external_id="SAMPLE-SPS-001").one().id


def test_map_record_incident_approved_returns_bundle(client):
    iid = _seed_incident_id()
    response = client.get(f"/api/map/record/reported_incident/{iid}")
    assert response.status_code == 200
    data = response.json()
    assert data["record_type"] == "reported_incident"
    assert data["id"] == iid
    assert "source_links" in data
    assert "news_articles" in data
    assert "related_court_records" in data
    assert "audit" in data
    assert "disclaimer" in data
    assert data["disclaimer"] != ""


def test_map_record_incident_pending_returns_404(client):
    iid = _seed_incident_id()
    with SessionLocal() as db:
        inc = db.query(CrimeIncident).filter_by(id=iid).one()
        orig_inc_review_p, orig_inc_pub_p = inc.review_status, inc.is_public
        inc.review_status = "pending_review"
        inc.is_public = False
        db.commit()
    try:
        assert client.get(f"/api/map/record/reported_incident/{iid}").status_code == 404
    finally:
        with SessionLocal() as db:
            inc2 = db.query(CrimeIncident).filter_by(id=iid).one()
            inc2.review_status = orig_inc_review_p
            inc2.is_public = orig_inc_pub_p
            db.commit()


def test_map_record_incident_disputed_returns_404(client):
    iid = _seed_incident_id()
    with SessionLocal() as db:
        inc = db.query(CrimeIncident).filter_by(id=iid).one()
        orig_inc_review_d, orig_inc_pub_d = inc.review_status, inc.is_public
        inc.review_status = "disputed"
        inc.is_public = False
        db.commit()
    try:
        assert client.get(f"/api/map/record/reported_incident/{iid}").status_code == 404
    finally:
        with SessionLocal() as db:
            inc2 = db.query(CrimeIncident).filter_by(id=iid).one()
            inc2.review_status = orig_inc_review_d
            inc2.is_public = orig_inc_pub_d
            db.commit()


def test_map_record_source_links_include_supports_claim(client):
    response = client.get("/api/map/record/court_event/EVT-SAMPLE-001")
    assert response.status_code == 200
    for link in response.json()["source_links"]:
        assert "supports_claim" in link
        assert "label" in link
        assert "url" in link
        assert "source_type" in link
        assert "retrieved_at" in link


def test_map_record_unverified_context_not_in_related(client):
    iid = _seed_incident_id()
    response = client.get(f"/api/map/record/reported_incident/{iid}")
    assert response.status_code == 200
    for entry in response.json().get("related_court_records", []):
        assert entry["relationship_status"] == "verified_source_link"


def test_map_record_unknown_record_type_returns_404(client):
    assert client.get("/api/map/record/unknown_type/1").status_code == 404
