from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.ingestion.adapters import ParsedRecord, RawRecord
from app.ingestion.courtlistener import CourtListenerAdapter
from app.ingestion.persistence import persist_parsed_record
from app.ingestion.runner import run_courtlistener_ingestion
from app.ingestion import runner as ingestion_runner
from app.models.entities import Case, Event, LegalSource, SourceSnapshot
from app.services.outcomes import create_verified_outcome
from app.services.text import normalize_docket


@pytest.fixture(autouse=True)
def reset_ingestion_lock():
    """Reset the ingestion lock before each test to prevent lock pollution."""
    # Force release the lock if it's held
    try:
        ingestion_runner._ingestion_lock.release()
    except RuntimeError:
        pass  # Lock was not held, which is fine
    yield
    # Clean up after test
    try:
        ingestion_runner._ingestion_lock.release()
    except RuntimeError:
        pass


@pytest.fixture(autouse=True)
def enable_courtlistener_source():
    """Enable courtlistener source registry entry for ingestion tests."""
    with SessionLocal() as db:
        from app.models.entities import SourceRegistry
        registry = db.query(SourceRegistry).filter_by(source_key="courtlistener").first()
        if registry is None:
            registry = SourceRegistry(
                source_key="courtlistener",
                source_name="CourtListener API",
                is_active=True,
                automation_status="machine_ready_enabled",
                requires_manual_review=True,
                auto_publish_enabled=False,
            )
            db.add(registry)
        else:
            registry.is_active = True
            registry.automation_status = "machine_ready_enabled"
        db.commit()
    yield


def test_source_verification_required_for_outcomes():
    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        news_source = db.query(LegalSource).filter_by(source_id="SRC-SAMPLE-005").one()
        with pytest.raises(ValueError):
            create_verified_outcome(
                db,
                event,
                "new_federal_charge",
                "Should not be accepted from unverified news.",
                news_source,
            )


def test_courtlistener_parse_isolates_bad_record():
    adapter = CourtListenerAdapter(token=None, base_url="https://example.test")
    raw_records = [
        RawRecord(source_name="courtlistener", payload={"docket_number": "1:24-cr-1", "court": "/api/rest/v4/courts/nysd/"}),
        RawRecord(source_name="courtlistener", payload=None),  # type: ignore[arg-type]
    ]
    parsed = 0
    errors = 0
    for raw in raw_records:
        try:
            adapter.parse(raw)
            parsed += 1
        except Exception:
            errors += 1
    assert parsed == 1
    assert errors == 1


def test_courtlistener_relative_urls_normalize_to_absolute():
    adapter = CourtListenerAdapter(token=None, base_url="https://www.courtlistener.com/api/rest/v4")
    parsed = adapter.parse(
        RawRecord(
            source_name="courtlistener",
            payload={
                "id": 123,
                "resource_uri": "/api/rest/v4/dockets/123/",
                "docket_number": "1:25-cr-1",
                "court": "/api/rest/v4/courts/nysd/",
                "case_name": "United States v. Sample",
                "docket_entries": [
                    {
                        "description": "Judgment as to sample defendant.",
                        "date_entered": "2025-01-03",
                        "recap_documents": [{"absolute_url": "/recap/gov.uscourts.nysd.123/doc.pdf"}],
                    }
                ],
            },
        )
    )
    assert parsed.source_api_url == "https://www.courtlistener.com/api/rest/v4/dockets/123/"
    assert parsed.document_links == ["https://www.courtlistener.com/recap/gov.uscourts.nysd.123/doc.pdf"]
    assert parsed.source_public_url == "https://www.courtlistener.com/recap/gov.uscourts.nysd.123/doc.pdf"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("absolute_url", "/docket/1/foo/"),
        ("frontend_url", "/docket/2/foo/"),
        ("docket_absolute_url", "/docket/3/foo/"),
    ],
)
def test_courtlistener_top_level_public_urls_normalize_to_absolute(field, value):
    adapter = CourtListenerAdapter(token=None, base_url="https://www.courtlistener.com/api/rest/v4")
    payload = {
        "id": 456,
        "resource_uri": "/api/rest/v4/dockets/456/",
        "docket_number": "1:25-cr-456",
        "court": "/api/rest/v4/courts/nysd/",
        "case_name": "United States v. URL Sample",
        field: value,
    }
    parsed = adapter.parse(RawRecord(source_name="courtlistener", payload=payload))
    assert parsed.source_api_url == "https://www.courtlistener.com/api/rest/v4/dockets/456/"
    assert parsed.source_public_url == f"https://www.courtlistener.com{value}"


def test_parsed_courtlistener_record_persists_case_source_event():
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="persist-1",
        docket_number="1:25-cr-777",
        court_code="nysd",
        caption="United States v. Persisted Sample",
        judge_name="SAMPLE Judge Avery Stone",
        docket_text="Judgment as to sample defendant. Sentenced to a sample term.",
        entry_date=datetime(2025, 1, 5, tzinfo=timezone.utc).date(),
        parties=[{"party_type": "defendant", "name": "Persisted Sample"}],
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/persist-1/",
        source_public_url="https://www.courtlistener.com/recap/persist-1/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        assert result.persisted is True
        assert result.event_id
        event = db.scalar(select(Event).where(Event.event_id == result.event_id))
        case = db.get(Case, result.case_id)
        source = db.get(LegalSource, result.source_id)
        assert event is not None
        assert case is not None
        assert source is not None
        assert case.docket_number == "1:25-cr-777"
        assert source.url == "https://www.courtlistener.com/recap/persist-1/"
        assert source.api_url == "https://www.courtlistener.com/api/rest/v4/dockets/persist-1/"


@pytest.mark.parametrize(
    ("source_quality", "expected_verified"),
    [
        ("secondary_context", False),
        ("court_record", True),
    ],
)
def test_persisted_source_verification_controls_last_verified_at(source_quality, expected_verified):
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id=f"verify-{source_quality}",
        docket_number=f"1:25-cr-verify-{source_quality}",
        court_code="nysd",
        caption=f"United States v. Verification {source_quality}",
        docket_text="Judgment as to verification sample. Sentenced to a sample term.",
        source_api_url=f"https://www.courtlistener.com/api/rest/v4/dockets/verify-{source_quality}/",
        source_public_url=f"https://www.courtlistener.com/recap/verify-{source_quality}/",
        source_quality=source_quality,
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        event = db.scalar(select(Event).where(Event.event_id == result.event_id))
        source = db.get(LegalSource, result.source_id)
        assert event is not None
        assert source is not None
        assert event.verified_flag is expected_verified
        assert source.verified_flag is expected_verified
        if expected_verified:
            assert event.last_verified_at is not None
        else:
            assert event.last_verified_at is None


def test_parsed_record_persistence_is_idempotent():
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="persist-2",
        docket_number="1:25-cr-778",
        court_code="nysd",
        caption="United States v. Idempotent Sample",
        docket_text="Order of detention entered. Detained pending trial.",
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/persist-2/",
        source_public_url="https://www.courtlistener.com/recap/persist-2/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        first = persist_parsed_record(db, parsed)
        second = persist_parsed_record(db, parsed)
        assert first.event_id == second.event_id
        assert db.scalars(select(Event).where(Event.event_id == first.event_id)).all()
        assert len(db.scalars(select(Event).where(Event.event_id == first.event_id)).all()) == 1


def test_ingestion_runner_persists_and_tracks_counts(monkeypatch):
    class FakeAdapter:
        errors: list[str] = []

        def fetch(self, since):
            return [RawRecord(source_name="courtlistener", payload={"id": "runner-1"})]

        def parse(self, raw):
            return ParsedRecord(
                source_name="courtlistener",
                docket_id="runner-1",
                docket_number="1:25-cr-779",
                court_code="nysd",
                caption="United States v. Runner Sample",
                docket_text="Judgment as to runner sample. Sentenced to a sample term.",
                source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/runner-1/",
                source_public_url="https://www.courtlistener.com/recap/runner-1/",
                source_quality="court_record",
            )

    monkeypatch.setattr("app.ingestion.runner.CourtListenerAdapter", FakeAdapter)
    with SessionLocal() as db:
        run = run_courtlistener_ingestion(db, datetime.now(timezone.utc))
        assert run.fetched_count == 1
        assert run.parsed_count == 1
        assert run.persisted_count == 1
        assert run.skipped_count == 0
        assert run.error_count == 0


def test_ingestion_runner_isolates_failed_record(monkeypatch):
    class FakeAdapter:
        errors: list[str] = []

        def fetch(self, since):
            return [
                RawRecord(source_name="courtlistener", payload={"docket": "ok-1"}),
                RawRecord(source_name="courtlistener", payload={"docket": "fail"}),
                RawRecord(source_name="courtlistener", payload={"docket": "ok-2"}),
            ]

        def parse(self, raw):
            docket = raw.payload["docket"]
            return ParsedRecord(
                source_name="courtlistener",
                docket_id=f"runner-{docket}",
                docket_number=f"1:25-cr-{docket}",
                court_code="nysd",
                caption=f"United States v. Runner {docket}",
                docket_text=f"Judgment as to runner {docket}. Sentenced to a sample term.",
                source_api_url=f"https://www.courtlistener.com/api/rest/v4/dockets/runner-{docket}/",
                source_public_url=f"https://www.courtlistener.com/recap/runner-{docket}/",
                source_quality="court_record",
            )

    original_persist = persist_parsed_record

    def flaky_persist(db, parsed):
        if parsed.docket_id == "runner-fail":
            original_persist(db, parsed)
            raise RuntimeError("forced record failure")
        return original_persist(db, parsed)

    monkeypatch.setattr("app.ingestion.runner.CourtListenerAdapter", FakeAdapter)
    monkeypatch.setattr("app.ingestion.runner.persist_parsed_record", flaky_persist)
    with SessionLocal() as db:
        run = run_courtlistener_ingestion(db, datetime.now(timezone.utc))
        assert run.fetched_count == 3
        assert run.parsed_count == 3
        assert run.persisted_count == 2
        assert run.error_count == 1
        assert db.scalar(select(Case).where(Case.normalized_docket_number == normalize_docket("1:25-cr-ok-1"))) is not None
        assert db.scalar(select(Case).where(Case.normalized_docket_number == normalize_docket("1:25-cr-ok-2"))) is not None
        assert db.scalar(select(Case).where(Case.normalized_docket_number == normalize_docket("1:25-cr-fail"))) is None


def test_one_docket_three_entries_creates_three_stable_events():
    adapter = CourtListenerAdapter(token=None, base_url="https://www.courtlistener.com/api/rest/v4")
    raw = RawRecord(
        source_name="courtlistener",
        payload={
            "id": "three-entry-docket",
            "resource_uri": "/api/rest/v4/dockets/three-entry-docket/",
            "docket_number": "1:25-cr-three",
            "court": "/api/rest/v4/courts/nysd/",
            "case_name": "United States v. Three Entry Sample",
            "docket_entries": [
                {"id": "entry-1", "entry_number": 1, "date_entered": "2025-01-10", "description": "Judgment as to defendant. Sentenced to a sample term."},
                {"id": "entry-2", "entry_number": 2, "date_entered": "2025-01-11", "description": "Order of detention entered. Detained pending trial."},
                {"id": "entry-3", "entry_number": 3, "date_entered": "2025-01-12", "description": "Judgment reversed. Conviction vacated and remanded for resentencing."},
            ],
        },
    )
    parsed_list = adapter.parse_many(raw)
    event_ids = set()
    with SessionLocal() as db:
        for parsed in parsed_list:
            result = persist_parsed_record(db, parsed)
            if result.event_id:
                event_ids.add(result.event_id)
        db.commit()

    assert len(parsed_list) == 3
    assert len(event_ids) == 3, "Each docket entry must produce a unique stable event ID"

    with SessionLocal() as db:
        for parsed in parsed_list:
            result2 = persist_parsed_record(db, parsed)
            if result2.event_id:
                assert result2.event_id in event_ids, "Rerunning same entries must not create new event IDs"
        db.commit()


def test_ingestion_rerun_is_idempotent():
    adapter = CourtListenerAdapter(token=None, base_url="https://www.courtlistener.com/api/rest/v4")
    raw = RawRecord(
        source_name="courtlistener",
        payload={
            "id": "rerun-idempotent-docket",
            "resource_uri": "/api/rest/v4/dockets/rerun-idempotent-docket/",
            "docket_number": "1:25-cr-rerun",
            "court": "/api/rest/v4/courts/nysd/",
            "case_name": "United States v. Rerun Idempotent Sample",
            "docket_entries": [
                {
                    "id": "rerun-entry-1",
                    "entry_number": 1,
                    "date_entered": "2025-02-01",
                    "description": "Judgment as to rerun sample. Sentenced to a sample term.",
                },
            ],
        },
    )
    parsed_list = adapter.parse_many(raw)
    with SessionLocal() as db:
        first_ids = {persist_parsed_record(db, p).event_id for p in parsed_list}
        db.commit()
    with SessionLocal() as db:
        second_ids = {persist_parsed_record(db, p).event_id for p in parsed_list}
        db.commit()

    assert first_ids == second_ids, "parse_many rerun must produce the same event IDs"
    with SessionLocal() as db:
        for event_id in first_ids:
            if event_id:
                count = len(db.scalars(select(Event).where(Event.event_id == event_id)).all())
                assert count == 1, f"Expected exactly one event for {event_id}, got {count}"


def test_unclassifiable_docket_entries_are_skipped():
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="unclassifiable-1",
        docket_number="1:25-cr-unclass",
        court_code="nysd",
        caption="United States v. Unclassifiable Sample",
        docket_text="Scheduling order entered. Clerk's notice of case assignment.",
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/unclass/",
        source_public_url="https://www.courtlistener.com/recap/unclass/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
    assert result.skipped is True
    assert result.event_id is None


# ---------------------------------------------------------------------------
# Phase 7: CourtListener pending-review safety tests
# ---------------------------------------------------------------------------

def test_courtlistener_persisted_event_defaults_to_pending_review():
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="pending-review-safety-1",
        docket_number="1:25-cr-pending-safety",
        court_code="nysd",
        caption="United States v. Pending Safety Sample",
        docket_text="Judgment as to Pending Safety Sample. Sentenced to a sample term.",
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/pending-safety/",
        source_public_url="https://www.courtlistener.com/recap/pending-safety/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        db.commit()
        assert result.event_id is not None
        event = db.scalar(select(Event).where(Event.event_id == result.event_id))
        assert event is not None
        assert event.review_status == "pending_review", (
            "CourtListener-ingested events must start as pending_review"
        )
        assert event.public_visibility is False, (
            "CourtListener-ingested events must not be publicly visible until reviewed"
        )


def test_courtlistener_persisted_event_not_on_public_map(client):
    parsed = ParsedRecord(
        source_name="courtlistener",
        docket_id="pending-review-map-gate-1",
        docket_number="1:25-cr-map-gate",
        court_code="nysd",
        caption="United States v. Map Gate Sample",
        docket_text="Judgment as to Map Gate Sample. Sentenced to a sample term.",
        source_api_url="https://www.courtlistener.com/api/rest/v4/dockets/map-gate/",
        source_public_url="https://www.courtlistener.com/recap/map-gate/",
        source_quality="court_record",
    )
    with SessionLocal() as db:
        result = persist_parsed_record(db, parsed)
        db.commit()

    assert result.event_id is not None
    map_response = client.get("/api/map/events")
    event_ids = {f["properties"]["event_id"] for f in map_response.json()["features"]}
    assert result.event_id not in event_ids, (
        "pending_review CourtListener event must not appear on the public map"
    )
    api_response = client.get(f"/api/events/{result.event_id}")
    assert api_response.status_code == 404, (
        "pending_review CourtListener event must return 404 from public events API"
    )


# ---------------------------------------------------------------------------
# Phase 8: Review audit history tests
# ---------------------------------------------------------------------------

def test_review_history_endpoint_requires_auth(client):
    response = client.get("/api/admin/review-history")
    assert response.status_code == 403


def test_review_decision_creates_evidence_review_audit_entry(client, monkeypatch):
    from app.api.routes import admin_review as ar
    from app.auth import admin as auth_admin

    class ReviewEnabledSettings:
        enable_admin_review = True
        enable_admin_imports = False
        enable_public_event_post = False
        admin_review_token = "test-review-token-p8"
        admin_token = None

    monkeypatch.setattr(auth_admin, "get_settings", lambda: ReviewEnabledSettings())
    monkeypatch.setattr(ar, "get_settings", lambda: ReviewEnabledSettings(), raising=False)

    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id="EVT-SAMPLE-001").one()
        snapshot = SourceSnapshot(
            source_url="https://example.com/review-audit-sample",
            fetched_at=datetime.now(timezone.utc),
            content_hash="a" * 64,
        )
        db.add(snapshot)
        db.flush()
        event.source_snapshot_id = snapshot.id
        db.commit()
        event_db_id = event.id

    response = client.post(
        "/api/admin/review-queue/event/EVT-SAMPLE-001/decision",
        json={"decision": "approve", "reviewed_by": "test-reviewer-p8", "notes": "Phase 8 test"},
        headers={"X-JTA-Admin-Token": "test-review-token-p8"},
    )
    assert response.status_code == 200

    history_response = client.get(
        "/api/admin/review-history",
        headers={"X-JTA-Admin-Token": "test-review-token-p8"},
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert "items" in history
    assert "total_count" in history
    assert history["total_count"] >= 1

    matching = [
        item for item in history["items"]
        if item["entity_type"] == "event" and item["entity_id"] == event_db_id
    ]
    assert len(matching) >= 1
    audit = matching[0]
    assert audit["new_status"] in ("verified_court_record",)
    assert audit["reviewed_by"] == "test-reviewer-p8"
    assert audit["reviewed_at"] is not None


def test_review_history_filters_by_entity_type(client, monkeypatch):
    from app.auth import admin as auth_admin

    class ReviewEnabledSettings:
        enable_admin_review = True
        enable_admin_imports = False
        enable_public_event_post = False
        admin_review_token = "test-review-token-p8b"
        admin_token = None

    monkeypatch.setattr(auth_admin, "get_settings", lambda: ReviewEnabledSettings())

    response = client.get(
        "/api/admin/review-history?entity_type=event",
        headers={"X-JTA-Admin-Token": "test-review-token-p8b"},
    )
    assert response.status_code == 200
    history = response.json()
    assert all(item["entity_type"] == "event" for item in history["items"])
