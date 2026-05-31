from datetime import date, datetime, timedelta, timezone

from app.models.entities import (
    Case,
    CaseParty,
    Court,
    CrimeIncident,
    Defendant,
    Event,
    EventDefendant,
    EventSource,
    Judge,
    LegalSource,
    Location,
    SourceSnapshot,
)
from app.services.linker import url_hash
from app.services.text import normalize_docket, normalize_name
from sqlalchemy import select, text
from sqlalchemy.orm import Session


def seed_sample_data(db: Session) -> None:
    """Seed sample data without explicit IDs to avoid sequence conflicts."""
    if db.scalar(select(Court).limit(1)):
        return
    now = datetime.now(timezone.utc)

    # Create locations first (no dependencies)
    locations = [
        Location(
            name="SAMPLE Daniel Patrick Moynihan U.S. Courthouse",
            city="New York",
            state="NY",
            region="Northeast",
            latitude=40.7143,
            longitude=-74.0021,
        ),
        Location(
            name="SAMPLE Dirksen U.S. Courthouse",
            city="Chicago",
            state="IL",
            region="Midwest",
            latitude=41.8789,
            longitude=-87.6300,
        ),
        Location(
            name="SAMPLE Edward R. Roybal Federal Building",
            city="Los Angeles",
            state="CA",
            region="West",
            latitude=34.0500,
            longitude=-118.2420,
        ),
    ]
    db.add_all(locations)
    db.flush()

    # Create courts (reference locations by object)
    courts = [
        Court(
            courtlistener_id="nysd",
            name="SAMPLE U.S. District Court, Southern District of New York",
            jurisdiction="Federal District",
            region="Northeast",
            location=locations[0],
        ),
        Court(
            courtlistener_id="ilnd",
            name="SAMPLE U.S. District Court, Northern District of Illinois",
            jurisdiction="Federal District",
            region="Midwest",
            location=locations[1],
        ),
        Court(
            courtlistener_id="cacd",
            name="SAMPLE U.S. District Court, Central District of California",
            jurisdiction="Federal District",
            region="West",
            location=locations[2],
        ),
    ]
    db.add_all(courts)
    db.flush()

    # Create judges (reference courts by object)
    judges = [
        Judge(
            name="SAMPLE Judge Avery Stone",
            normalized_name=normalize_name("SAMPLE Judge Avery Stone"),
            court=courts[0],
        ),
        Judge(
            name="SAMPLE Judge Morgan Reed",
            normalized_name=normalize_name("SAMPLE Judge Morgan Reed"),
            court=courts[1],
        ),
        Judge(
            name="SAMPLE Judge Jordan Hale",
            normalized_name=normalize_name("SAMPLE Judge Jordan Hale"),
            court=courts[2],
        ),
    ]
    db.add_all(judges)
    db.flush()

    # Create cases (reference courts by object)
    cases = [
        Case(
            court=courts[0],
            docket_number="1:24-cr-00001",
            normalized_docket_number=normalize_docket("1:24-cr-00001"),
            caption="SAMPLE United States v. Alpha",
            case_type="criminal",
            filed_date=date(2024, 1, 12),
            courtlistener_docket_id="sample-1001",
        ),
        Case(
            court=courts[0],
            docket_number="1:24-cr-00002",
            normalized_docket_number=normalize_docket("1:24-cr-00002"),
            caption="SAMPLE United States v. Beta",
            case_type="criminal",
            filed_date=date(2024, 2, 2),
            courtlistener_docket_id="sample-1002",
        ),
        Case(
            court=courts[1],
            docket_number="1:24-cr-00003",
            normalized_docket_number=normalize_docket("1:24-cr-00003"),
            caption="SAMPLE United States v. Gamma",
            case_type="criminal",
            filed_date=date(2024, 3, 8),
            courtlistener_docket_id="sample-1003",
        ),
        Case(
            court=courts[2],
            docket_number="2:24-cr-00004",
            normalized_docket_number=normalize_docket("2:24-cr-00004"),
            caption="SAMPLE United States v. Delta",
            case_type="criminal",
            filed_date=date(2024, 4, 17),
            courtlistener_docket_id="sample-1004",
        ),
        Case(
            court=courts[2],
            docket_number="2:24-cr-00005",
            normalized_docket_number=normalize_docket("2:24-cr-00005"),
            caption="SAMPLE United States v. Echo",
            case_type="criminal",
            filed_date=date(2024, 5, 21),
            courtlistener_docket_id="sample-1005",
        ),
    ]
    db.add_all(cases)
    db.flush()

    # Create defendants
    defendants = [
        Defendant(
            anonymized_id="DEF-000001",
            public_name="Sample Alpha",
            normalized_public_name=normalize_name("Sample Alpha"),
        ),
        Defendant(
            anonymized_id="DEF-000002",
            public_name="Sample Beta",
            normalized_public_name=normalize_name("Sample Beta"),
        ),
        Defendant(
            anonymized_id="DEF-000003",
            public_name="Sample Gamma",
            normalized_public_name=normalize_name("Sample Gamma"),
        ),
    ]
    db.add_all(defendants)
    db.flush()

    # Create case parties (reference cases and defendants by object)
    parties = [
        CaseParty(
            case=cases[0],
            defendant=defendants[0],
            party_type="defendant",
            public_name="Sample Alpha",
            normalized_name=normalize_name("Sample Alpha"),
        ),
        CaseParty(
            case=cases[1],
            defendant=defendants[1],
            party_type="defendant",
            public_name="Sample Beta",
            normalized_name=normalize_name("Sample Beta"),
        ),
        CaseParty(
            case=cases[2],
            defendant=defendants[2],
            party_type="defendant",
            public_name="Sample Gamma",
            normalized_name=normalize_name("Sample Gamma"),
        ),
        CaseParty(
            case=cases[3],
            defendant=defendants[0],
            party_type="defendant",
            public_name="Sample Alpha",
            normalized_name=normalize_name("Sample Alpha"),
        ),
        CaseParty(
            case=cases[4],
            defendant=defendants[1],
            party_type="defendant",
            public_name="Sample Beta",
            normalized_name=normalize_name("Sample Beta"),
        ),
    ]
    db.add_all(parties)
    db.flush()

    # Create legal sources
    sources = [
        LegalSource(
            source_id="SRC-SAMPLE-001",
            source_type="court_record",
            title="SAMPLE docket entry 12",
            url="https://courtlistener.example/sample/1001/12",
            url_hash=url_hash("https://courtlistener.example/sample/1001/12"),
            source_quality="court_record",
            verified_flag=True,
            retrieved_at=datetime.now(timezone.utc),
        ),
        LegalSource(
            source_id="SRC-SAMPLE-002",
            source_type="court_order",
            title="SAMPLE order of detention",
            url="https://courtlistener.example/sample/1002/8",
            url_hash=url_hash("https://courtlistener.example/sample/1002/8"),
            source_quality="court_order",
            verified_flag=True,
            retrieved_at=datetime.now(timezone.utc),
        ),
        LegalSource(
            source_id="SRC-SAMPLE-003",
            source_type="appeal_decision",
            title="SAMPLE appeal decision",
            url="https://courtlistener.example/sample/1003/appeal",
            url_hash=url_hash("https://courtlistener.example/sample/1003/appeal"),
            source_quality="appeal_decision",
            verified_flag=True,
            retrieved_at=datetime.now(timezone.utc),
        ),
        LegalSource(
            source_id="SRC-SAMPLE-004",
            source_type="official_statement",
            title="SAMPLE official release",
            url="https://justice.example/sample/release",
            url_hash=url_hash("https://justice.example/sample/release"),
            source_quality="official_statement",
            verified_flag=True,
            retrieved_at=datetime.now(timezone.utc),
        ),
        LegalSource(
            source_id="SRC-SAMPLE-005",
            source_type="news",
            title="SAMPLE secondary context article",
            url="https://news.example/sample/context",
            url_hash=url_hash("https://news.example/sample/context"),
            source_quality="secondary_context",
            verified_flag=False,
            retrieved_at=datetime.now(timezone.utc),
        ),
    ]
    db.add_all(sources)
    db.flush()

    # Create events (reference courts, judges, cases, locations by object)
    events = [
        Event(
            event_id="EVT-SAMPLE-001",
            court=courts[0],
            judge=judges[0],
            case=cases[0],
            primary_location=locations[0],
            event_type="detention_order",
            event_subtype="pretrial",
            decision_result="detained",
            decision_date=date(2024, 1, 15),
            posted_date=date(2024, 1, 16),
            title="SAMPLE order of detention",
            summary="SAMPLE court record states order of detention under 18 U.S.C. § 3142.",
            repeat_offender_indicator=True,
            verified_flag=True,
            source_quality="court_record",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-002",
            court=courts[0],
            judge=judges[0],
            case=cases[1],
            primary_location=locations[0],
            event_type="release_order",
            event_subtype="conditions",
            decision_result="released on conditions",
            decision_date=date(2024, 2, 5),
            posted_date=date(2024, 2, 6),
            title="SAMPLE release on conditions",
            summary="SAMPLE docket text states released on conditions.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-003",
            court=courts[1],
            judge=judges[1],
            case=cases[2],
            primary_location=locations[1],
            event_type="sentencing",
            event_subtype="judgment",
            decision_result="sentenced",
            decision_date=date(2024, 3, 22),
            posted_date=date(2024, 3, 24),
            title="SAMPLE judgment as to defendant",
            summary="SAMPLE judgment as to defendant; sentenced to a sample term.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-004",
            court=courts[2],
            judge=judges[2],
            case=cases[3],
            primary_location=locations[2],
            event_type="revocation",
            event_subtype="supervised_release",
            decision_result="revoked",
            decision_date=date(2024, 4, 30),
            posted_date=date(2024, 5, 1),
            title="SAMPLE supervised release revoked",
            summary="SAMPLE order says supervised release revoked after violation.",
            repeat_offender_indicator=True,
            verified_flag=True,
            source_quality="court_order",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-005",
            court=courts[2],
            judge=judges[2],
            case=cases[4],
            primary_location=locations[2],
            event_type="motion_to_suppress",
            event_subtype="motion",
            decision_result="pending",
            decision_date=date(2024, 5, 27),
            posted_date=date(2024, 5, 28),
            title="SAMPLE motion to suppress",
            summary="SAMPLE motion to suppress filed.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-006",
            court=courts[1],
            judge=judges[1],
            case=cases[2],
            primary_location=locations[1],
            event_type="appeal_reversal",
            event_subtype="appeal",
            decision_result="reversed",
            decision_date=date(2024, 8, 3),
            posted_date=date(2024, 8, 4),
            title="SAMPLE appeal reversed",
            summary="SAMPLE appellate source says reversed.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="appeal_decision",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-007",
            court=courts[0],
            judge=judges[0],
            case=cases[0],
            primary_location=locations[0],
            event_type="indictment",
            event_subtype="charging",
            decision_result="filed",
            decision_date=date(2024, 1, 12),
            posted_date=date(2024, 1, 12),
            title="SAMPLE indictment filed",
            summary="SAMPLE indictment entered on docket.",
            repeat_offender_indicator=False,
            verified_flag=True,
            source_quality="court_record",
            last_verified_at=now,
            classifier_metadata={"sample": True},
        ),
        Event(
            event_id="EVT-SAMPLE-008",
            court=courts[2],
            judge=None,
            case=cases[4],
            primary_location=locations[2],
            event_type="news_coverage",
            event_subtype="secondary_context",
            decision_result=None,
            decision_date=date(2024, 6, 3),
            posted_date=date(2024, 6, 3),
            title="SAMPLE secondary news context",
            summary="SAMPLE news coverage retained only as secondary context.",
            repeat_offender_indicator=False,
            verified_flag=False,
            source_quality="secondary_context",
            last_verified_at=None,
            classifier_metadata={"sample": True},
        ),
    ]

    incident_snapshots = [
        SourceSnapshot(
            source_key="sample_saskatoon_police",
            source_url="https://map.saskatoonpolice.ca/",
            fetched_at=now,
            content_hash="1" * 64,
            raw_content="sample saskatoon police public incident evidence",
        ),
        SourceSnapshot(
            source_key="sample_toronto_police",
            source_url="https://www.tps.ca/data-maps/",
            fetched_at=now,
            content_hash="2" * 64,
            raw_content="sample toronto police public incident evidence",
        ),
        SourceSnapshot(
            source_key="sample_chicago_data",
            source_url="https://data.cityofchicago.org/",
            fetched_at=now,
            content_hash="3" * 64,
            raw_content="sample chicago public incident evidence",
        ),
        SourceSnapshot(
            source_key="sample_los_angeles_data",
            source_url="https://data.lacity.org/",
            fetched_at=now,
            content_hash="4" * 64,
            raw_content="sample los angeles public incident evidence",
        ),
    ]

    # Attach events to the session before any flush so relationship backrefs do not
    # warn during autoflush when courts/cases/judges are already persistent.
    db.add_all(events)
    db.add_all(incident_snapshots)
    db.flush()

    # Create crime incidents without explicit IDs
    crime_incidents = [
        CrimeIncident(
            source_id="SAMPLE-SPS",
            external_id="SAMPLE-SPS-001",
            incident_type="SAMPLE Assault",
            incident_category="violent",
            reported_at=now - timedelta(hours=12),
            occurred_at=now - timedelta(hours=16),
            city="Saskatoon",
            province_state="SK",
            country="Canada",
            public_area_label="Downtown Saskatoon",
            latitude_public=52.1332,
            longitude_public=-106.6702,
            precision_level="general_area",
            source_url="https://map.saskatoonpolice.ca/",
            source_name="SAMPLE Saskatoon Police Service",
            verification_status="reported",
            data_last_seen_at=now,
            is_public=True,
            source_snapshot_id=incident_snapshots[0].id,
            notes="SAMPLE generalized public-area incident. Not adjudicated.",
        ),
        CrimeIncident(
            source_id="SAMPLE-TPS",
            external_id="SAMPLE-TPS-001",
            incident_type="SAMPLE Break and enter",
            incident_category="property",
            reported_at=now - timedelta(days=1),
            occurred_at=now - timedelta(days=1, hours=12),
            city="Toronto",
            province_state="ON",
            country="Canada",
            public_area_label="Downtown Toronto",
            latitude_public=43.6532,
            longitude_public=-79.3832,
            precision_level="neighbourhood_centroid",
            source_url="https://www.tps.ca/data-maps/",
            source_name="SAMPLE Toronto Police Service Public Safety Data Portal",
            verification_status="reported",
            data_last_seen_at=now,
            is_public=True,
            source_snapshot_id=incident_snapshots[1].id,
            notes="SAMPLE generalized public-area incident. Not adjudicated.",
        ),
        CrimeIncident(
            source_id="SAMPLE-CHI",
            external_id="SAMPLE-CHI-001",
            incident_type="SAMPLE Theft",
            incident_category="property",
            reported_at=now - timedelta(days=5),
            occurred_at=now - timedelta(days=5, hours=18),
            city="Chicago",
            province_state="IL",
            country="United States",
            public_area_label="Loop community area",
            latitude_public=41.8781,
            longitude_public=-87.6298,
            precision_level="community_area_centroid",
            source_url="https://data.cityofchicago.org/",
            source_name="SAMPLE Chicago Data Portal",
            verification_status="reported",
            data_last_seen_at=now,
            is_public=True,
            source_snapshot_id=incident_snapshots[2].id,
            notes="SAMPLE generalized public-area incident. Not adjudicated.",
        ),
        CrimeIncident(
            source_id="SAMPLE-LA",
            external_id="SAMPLE-LA-001",
            incident_type="SAMPLE Robbery",
            incident_category="violent",
            reported_at=now - timedelta(days=15),
            occurred_at=now - timedelta(days=15, hours=9),
            city="Los Angeles",
            province_state="CA",
            country="United States",
            public_area_label="Downtown Los Angeles",
            latitude_public=34.0522,
            longitude_public=-118.2437,
            precision_level="general_area",
            source_url="https://data.lacity.org/",
            source_name="SAMPLE Los Angeles Open Data",
            verification_status="reported",
            data_last_seen_at=now,
            is_public=True,
            source_snapshot_id=incident_snapshots[3].id,
            notes="SAMPLE generalized public-area incident. Not adjudicated.",
        ),
    ]

    for source in sources:
        source.review_status = (
            "news_only_context"
            if source.source_type == "news"
            else "verified_court_record"
        )
        source.reviewed_by = "SAMPLE reviewer"
        source.reviewed_at = datetime.now(timezone.utc)
        source.public_visibility = True

    for event in events:
        event.review_status = (
            "news_only_context"
            if event.event_type == "news_coverage"
            else "verified_court_record"
        )
        event.reviewed_by = "SAMPLE reviewer"
        event.reviewed_at = datetime.now(timezone.utc)
        event.public_visibility = True

    for incident in crime_incidents:
        incident.review_status = "official_police_open_data_report"
        incident.reviewed_by = "SAMPLE reviewer"
        incident.reviewed_at = datetime.now(timezone.utc)

    db.add_all(crime_incidents)
    db.flush()

    # Create event-defendant links using object references
    event_links = [
        EventDefendant(event=events[0], defendant=defendants[0]),
        EventDefendant(event=events[1], defendant=defendants[1]),
        EventDefendant(event=events[2], defendant=defendants[2]),
        EventDefendant(event=events[3], defendant=defendants[0]),
        EventDefendant(event=events[4], defendant=defendants[1]),
        EventDefendant(event=events[5], defendant=defendants[2]),
        EventDefendant(event=events[6], defendant=defendants[0]),
        EventDefendant(event=events[7], defendant=defendants[1]),
    ]

    # Create event-source links using object references
    source_links = [
        EventSource(event=events[0], source=sources[1]),
        EventSource(event=events[1], source=sources[0]),
        EventSource(event=events[2], source=sources[0]),
        EventSource(event=events[3], source=sources[1]),
        EventSource(event=events[4], source=sources[0]),
        EventSource(event=events[5], source=sources[2], supports_outcome=True),
        EventSource(event=events[6], source=sources[0]),
        EventSource(event=events[7], source=sources[4]),
    ]
    db.add_all(event_links + source_links)
    db.commit()

    # Reset sequences after seeding (Postgres compatibility)
    reset_postgres_sequences(db)


def reset_postgres_sequences(db: Session) -> None:
    """Sync Postgres sequences to the current max IDs after seeding.

    Seed data now uses ORM-assigned IDs (no explicit integers), so this is
    a defensive sync rather than a required fix. It is a no-op on SQLite.
    """
    # Get the max ID from each table and reset the sequence
    tables = [
        "locations",
        "courts",
        "judges",
        "cases",
        "defendants",
        "legal_sources",
        "events",
        "crime_incidents",
        "review_items",
        "audit_logs",
    ]
    for table in tables:
        try:
            # Reset sequence to max(id) + 1
            db.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                    false
                )
            """))
        except Exception:
            # Silently ignore if table doesn't exist or isn't Postgres
            pass
    db.commit()


def verify_seed_correctness(db: Session) -> bool:
    """Verify that seed data allows new inserts without ID collisions.

    Returns True if a new Location, Court, Event, and CrimeIncident
    can be inserted after seeding without duplicate-key failures.
    """
    import uuid

    from app.models.entities import Case, Court, CrimeIncident, Event, Location
    from sqlalchemy import select

    unique = uuid.uuid4().hex[:12]
    try:
        # Attempt to insert new records
        test_location = Location(
            name=f"TEST Location {unique}",
            city="Test City",
            latitude=0.0,
            longitude=0.0,
        )
        db.add(test_location)
        db.flush()

        test_court = Court(
            courtlistener_id=f"test-court-{unique}",
            name=f"Test Court {unique}",
            location=test_location,
        )
        db.add(test_court)
        db.flush()

        # Get an existing case for the event relationship
        existing_case = db.scalar(select(Case).limit(1))
        if existing_case is None:
            db.rollback()
            return False

        test_event = Event(
            event_id=f"TEST-EVENT-{unique}",
            event_type="test_event",
            title="Test event verify seed",
            summary="Test summary for seed correctness check.",
            court=test_court,
            case=existing_case,
            primary_location=test_location,
        )
        db.add(test_event)
        db.flush()

        test_incident = CrimeIncident(
            source_name="TEST",
            external_id=f"TEST-{unique}",
            incident_type="Test Incident",
            incident_category="other",
            precision_level="city_centroid",
            latitude_public=0.0,
            longitude_public=0.0,
        )
        db.add(test_incident)
        db.flush()

        # Rollback test data
        db.rollback()
        return True
    except Exception:
        db.rollback()
        return False
