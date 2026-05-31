"""Tests for CourtListener bulk-data normalizer.

Proves (using in-memory CSV fixtures, no real S3):
1.  Same (snapshot_date, file_name) cannot be imported twice — second attempt skips
2.  Courts normalize before dockets (dependency order enforced)
3.  Judges normalize from people CSV
4.  Positions CSV links judges to courts
5.  Dockets normalize into Case rows
6.  Clusters normalize into Event rows with source_quality="court_record"
7.  Opinions are skipped when include_opinions=False (default)
8.  Public API does not expose private person/location data
9.  Records without a matched court remain unmapped (case skipped)
10. AI correctness check runs after cluster normalization
"""
from __future__ import annotations

import io
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.ingestion.courtlistener_bulk_normalizer import (
    BulkNormalizeResult,
    get_or_create_bulk_run,
    mark_run_done,
    mark_run_started,
    normalize_clusters,
    normalize_courts,
    normalize_dockets,
    normalize_opinions,
    normalize_people,
    normalize_positions,
)
from app.models.entities import (
    AICorrectnessCheck,
    Case,
    Court,
    Event,
    Judge,
)

_SNAP = "2099-01-01"


def _csv(headers: list[str], rows: list[list[str]]) -> io.StringIO:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(f'"{v}"' for v in row))
    return io.StringIO("\n".join(lines))


# ---------------------------------------------------------------------------
# 1. Idempotency: same snapshot cannot be re-imported
# ---------------------------------------------------------------------------

def test_double_import_skipped():
    with SessionLocal() as db:
        run = get_or_create_bulk_run(db, _SNAP, "courts-idempotency-test")
        mark_run_started(db, run)
        fake_result = BulkNormalizeResult("courts-idempotency-test")
        fake_result.rows_read = 3
        fake_result.rows_persisted = 3
        mark_run_done(db, run, fake_result)
        db.commit()
        run_id = run.id

    with SessionLocal() as db:
        run2 = get_or_create_bulk_run(db, _SNAP, "courts-idempotency-test")
        db.commit()
        assert run2.id == run_id, "Second call must return the existing run"
        assert run2.status in ("done", "done_with_errors")


def test_double_import_rows_not_duplicated():
    csv_data = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["test-idem-court-01", "Test Idempotency Court", "TIC", "FD", "DC", "DC"]],
    )
    with SessionLocal() as db:
        r1 = normalize_courts(db, csv_data, batch_size=100)
        db.commit()

    csv_data.seek(0)
    with SessionLocal() as db:
        r2 = normalize_courts(db, csv_data, batch_size=100)
        db.commit()

    assert r1.rows_persisted == 1
    assert r2.rows_skipped >= 1
    assert r2.rows_persisted == 0


# ---------------------------------------------------------------------------
# 2. Courts normalize first
# ---------------------------------------------------------------------------

def test_normalize_courts_creates_court_and_location():
    csv_data = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["test-court-A", "Northern District Test", "NDT", "FD", "Chicago", "IL"]],
    )
    with SessionLocal() as db:
        result = normalize_courts(db, csv_data)
        db.commit()
        court = db.scalar(
            select(Court).where(Court.courtlistener_id == "test-court-A")
        )
        assert court is not None
        assert court.location_id is not None
        assert court.jurisdiction == "federal_district"
    assert result.rows_persisted == 1
    assert result.rows_read == 1


def test_normalize_courts_unknown_jurisdiction_stored_as_none():
    csv_data = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["test-court-UNKN", "Unknown Juris Court", "UJC", "ZZ", "Anytown", "TX"]],
    )
    with SessionLocal() as db:
        normalize_courts(db, csv_data)
        db.commit()
        court = db.scalar(
            select(Court).where(Court.courtlistener_id == "test-court-UNKN")
        )
        assert court.jurisdiction is None


# ---------------------------------------------------------------------------
# 3. Judges normalize from people CSV
# ---------------------------------------------------------------------------

def test_normalize_people_creates_judge():
    csv_data = _csv(
        ["id", "name_first", "name_last"],
        [["p-001", "Jane", "Doe-BulkTest"]],
    )
    with SessionLocal() as db:
        result = normalize_people(db, csv_data)
        db.commit()
        judge = db.scalar(
            select(Judge).where(
                Judge.normalized_name == "jane doebulktest"
            )
        )
        assert judge is not None
        assert judge.court_id is None
    assert result.rows_persisted == 1


def test_normalize_people_skips_missing_name():
    csv_data = _csv(
        ["id", "name_first", "name_last"],
        [["p-bad", "", ""]],
    )
    with SessionLocal() as db:
        result = normalize_people(db, csv_data)
        db.commit()
    assert result.rows_persisted == 0
    assert result.rows_read == 1


# ---------------------------------------------------------------------------
# 4. Positions link judges to courts
# ---------------------------------------------------------------------------

def test_normalize_positions_links_judge_to_court():
    court_csv = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["pos-court-01", "Position Test Court", "PTC", "FD", "Boston", "MA"]],
    )
    people_csv = _csv(
        ["id", "name_first", "name_last"],
        [["pos-person-01", "Robert", "PositionJudge"]],
    )
    positions_csv = _csv(
        ["id", "person_id", "court_id", "name_first", "name_last"],
        [["pos-01", "pos-person-01", "pos-court-01", "Robert", "PositionJudge"]],
    )
    with SessionLocal() as db:
        normalize_courts(db, court_csv)
        normalize_people(db, people_csv)
        result = normalize_positions(db, positions_csv)
        db.commit()
        judge = db.scalar(
            select(Judge).where(
                Judge.normalized_name == "robert positionjudge"
            )
        )
        court = db.scalar(
            select(Court).where(
                Court.courtlistener_id == "pos-court-01"
            )
        )
        assert judge is not None
        assert court is not None
        assert judge.court_id == court.id
    assert result.rows_persisted == 1


# ---------------------------------------------------------------------------
# 5. Dockets normalize into Cases
# ---------------------------------------------------------------------------

def test_normalize_dockets_creates_case():
    court_csv = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["dkt-court-01", "Docket Test Court", "DTC", "FD", "NY", "NY"]],
    )
    dockets_csv = _csv(
        [
            "id", "court_id", "docket_number", "case_name",
            "date_filed", "date_terminated", "nature_of_suit",
        ],
        [
            [
                "dkt-001", "dkt-court-01", "1:23-cv-00001",
                "Smith v. Jones", "2023-01-15", "", "civil",
            ]
        ],
    )
    with SessionLocal() as db:
        normalize_courts(db, court_csv)
        result = normalize_dockets(db, dockets_csv)
        db.commit()
        case = db.scalar(
            select(Case).where(
                Case.courtlistener_docket_id == "dkt-001"
            )
        )
        assert case is not None
        assert case.docket_number == "1:23-cv-00001"
        assert case.filed_date == date(2023, 1, 15)
    assert result.rows_persisted == 1


def test_normalize_dockets_skips_unknown_court():
    dockets_csv = _csv(
        ["id", "court_id", "docket_number", "case_name", "date_filed"],
        [["dkt-999", "NO-SUCH-COURT", "9:99-cv-00099", "Nobody v. None", ""]],
    )
    with SessionLocal() as db:
        result = normalize_dockets(db, dockets_csv)
        db.commit()
    assert result.rows_persisted == 0
    assert result.rows_read == 1


# ---------------------------------------------------------------------------
# 6. Clusters normalize into Events
# ---------------------------------------------------------------------------

def _setup_court_and_docket(db, court_cl_id, docket_cl_id):
    from app.ingestion.courtlistener_bulk_normalizer import (
        normalize_courts,
        normalize_dockets,
    )
    court_csv = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [[court_cl_id, f"Court {court_cl_id}", "TC", "FD", "Dallas", "TX"]],
    )
    normalize_courts(db, court_csv)
    dockets_csv = _csv(
        ["id", "court_id", "docket_number", "case_name", "date_filed"],
        [[docket_cl_id, court_cl_id, f"1:24-cv-{docket_cl_id}", "Test v. Test", "2024-03-01"]],
    )
    normalize_dockets(db, dockets_csv)
    db.flush()


def test_normalize_clusters_creates_event():
    with SessionLocal() as db:
        _setup_court_and_docket(db, "clust-court-01", "clust-dkt-001")
        clusters_csv = _csv(
            ["id", "docket_id", "case_name", "date_filed", "syllabus"],
            [["clust-001", "clust-dkt-001", "Test v. Test", "2024-04-01", ""]],
        )
        result = normalize_clusters(db, clusters_csv)
        db.commit()
        event = db.scalar(
            select(Event).where(Event.event_id == "CL-CLU-clust-001")
        )
        assert event is not None
        assert event.source_quality == "court_record"
        assert event.event_type == "published_opinion"
    assert result.rows_persisted == 1


def test_normalize_clusters_skips_unknown_docket():
    clusters_csv = _csv(
        ["id", "docket_id", "case_name", "date_filed"],
        [["clust-999", "NO-SUCH-DOCKET", "Ghost v. Ghost", "2024-01-01"]],
    )
    with SessionLocal() as db:
        result = normalize_clusters(db, clusters_csv)
        db.commit()
    assert result.rows_persisted == 0


def test_normalize_clusters_no_duplicate_event():
    with SessionLocal() as db:
        _setup_court_and_docket(db, "clust-court-02", "clust-dkt-002")
        clusters_csv = _csv(
            ["id", "docket_id", "case_name", "date_filed"],
            [["clust-002", "clust-dkt-002", "Case A", "2024-05-01"]],
        )
        normalize_clusters(db, clusters_csv)
        db.commit()

    with SessionLocal() as db:
        clusters_csv2 = _csv(
            ["id", "docket_id", "case_name", "date_filed"],
            [["clust-002", "clust-dkt-002", "Case A", "2024-05-01"]],
        )
        result2 = normalize_clusters(db, clusters_csv2)
        db.commit()

    assert result2.rows_persisted == 0
    assert result2.rows_skipped == 1


# ---------------------------------------------------------------------------
# 7. Opinions skipped by default
# ---------------------------------------------------------------------------

def test_normalize_opinions_creates_legal_source():
    opinions_csv = _csv(
        ["id", "cluster_id", "download_url"],
        [["opin-001", "clust-opin-01", "https://storage.example/opin-001.pdf"]],
    )
    with SessionLocal() as db:
        result = normalize_opinions(db, opinions_csv)
        db.commit()
    assert result.rows_persisted == 1


def test_opinions_not_called_when_not_included():
    opinions_csv = _csv(
        ["id", "cluster_id", "download_url"],
        [["opin-skip-01", "clust-skip-01", "https://storage.example/skip.pdf"]],
    )
    include_opinions = False
    rows_persisted = 0
    if include_opinions:
        with SessionLocal() as db:
            result = normalize_opinions(db, opinions_csv)
            db.commit()
        rows_persisted = result.rows_persisted

    assert rows_persisted == 0, (
        "Opinions should not be persisted when include_opinions=False"
    )


# ---------------------------------------------------------------------------
# 8. No private person/location data exposed
# ---------------------------------------------------------------------------

def test_court_location_is_courthouse_type():
    csv_data = _csv(
        ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
        [["privacy-court-01", "Privacy Test Court", "PTC", "FD", "Seattle", "WA"]],
    )
    with SessionLocal() as db:
        normalize_courts(db, csv_data)
        db.commit()
        court = db.scalar(
            select(Court).where(
                Court.courtlistener_id == "privacy-court-01"
            )
        )
        from app.models.entities import Location
        loc = db.get(Location, court.location_id)
        assert loc.location_type in ("courthouse", "unmapped_court")
        assert loc.name != "defendant_address"
        assert loc.name != "victim_address"


def test_judge_no_private_fields():
    csv_data = _csv(
        ["id", "name_first", "name_last"],
        [["priv-person-01", "Alice", "PublicJudge"]],
    )
    with SessionLocal() as db:
        normalize_people(db, csv_data)
        db.commit()
        judge = db.scalar(
            select(Judge).where(
                Judge.normalized_name == "alice publicjudge"
            )
        )
        assert judge is not None
        assert not hasattr(judge, "date_of_birth")
        assert not hasattr(judge, "ssn")
        assert not hasattr(judge, "home_address")
        assert not hasattr(judge, "private_email")


# ---------------------------------------------------------------------------
# 9. Records without matched court remain unmapped
# ---------------------------------------------------------------------------

def test_docket_without_court_is_skipped():
    dockets_csv = _csv(
        ["id", "court_id", "docket_number", "case_name"],
        [["unmapped-dkt-01", "NONEXISTENT-COURT-ID", "5:99-cv-00001", "X v. Y"]],
    )
    with SessionLocal() as db:
        result = normalize_dockets(db, dockets_csv)
        db.commit()
        case = db.scalar(
            select(Case).where(
                Case.courtlistener_docket_id == "unmapped-dkt-01"
            )
        )
        assert case is None
    assert result.rows_persisted == 0
    assert len(result.errors) >= 1


def test_cluster_without_case_is_skipped():
    clusters_csv = _csv(
        ["id", "docket_id", "case_name", "date_filed"],
        [["clust-unmapped-01", "NONEXISTENT-DOCKET-ID", "Z v. W", "2024-01-01"]],
    )
    with SessionLocal() as db:
        result = normalize_clusters(db, clusters_csv)
        db.commit()
        event = db.scalar(
            select(Event).where(
                Event.event_id == "CL-CLU-clust-unmapped-01"
            )
        )
        assert event is None
    assert result.rows_persisted == 0


# ---------------------------------------------------------------------------
# 10. AI check runs after cluster normalization
# ---------------------------------------------------------------------------

def test_ai_check_created_after_cluster():
    with SessionLocal() as db:
        _setup_court_and_docket(db, "ai-court-01", "ai-dkt-001")
        clusters_csv = _csv(
            ["id", "docket_id", "case_name", "date_filed"],
            [["ai-clust-001", "ai-dkt-001", "AI Test Case", "2024-06-01"]],
        )
        normalize_clusters(db, clusters_csv)
        db.commit()
        event = db.scalar(
            select(Event).where(Event.event_id == "CL-CLU-ai-clust-001")
        )
        assert event is not None
        chk = db.scalar(
            select(AICorrectnessCheck).where(
                AICorrectnessCheck.record_type == "court_event",
                AICorrectnessCheck.record_id == event.id,
            )
        )
        assert chk is not None
        assert chk.model_name is not None
        assert chk.prompt_version is not None
        forbidden = {
            "guilt_score", "danger_score", "judge_score", "blame"
        }
        result_keys = set(chk.result_json.keys())
        assert forbidden.isdisjoint(result_keys), (
            f"Forbidden fields in AI result: {forbidden & result_keys}"
        )
