"""CourtListener bulk-data normalizer.

Streams CourtListener quarterly-snapshot CSVs row-by-row (no staging DB)
and normalizes them into JudgeTracker's existing tables.

File dependency order (must respect):
  1. courts        → Court + Location
  2. people        → Judge (identity only)
  3. positions     → Judge.court_id update
  4. dockets       → Case
  5. clusters      → Event (court_event)
  6. opinions      → LegalSource (optional)

After each cluster/event, an AI correctness check is run.
All bulk records land with public_visibility=False / pending_review.
Human admin review is required to publish — bulk ingestion never auto-publishes.

Public safety rules:
- Location mapped only to courthouse level — never defendant/victim address.
- No private person data stored beyond publicly-known judge names.
- Opinion text is not stored — only URL and metadata.
"""
from __future__ import annotations

import csv
import io
import logging
import pathlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.ingestion.source_keys import COURTLISTENER_BULK
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    CLBulkProvenance,
    Case,
    Court,
    CourtListenerBulkRun,
    Event,
    EventSource,
    Judge,
    LegalSource,
    Location,
)
from app.services.ai_correctness import check_court_event
from app.services.linker import url_hash
from app.services.text import normalize_docket, normalize_name
from app.ingestion.statuses import FAILED, PENDING, RUNNING

log = logging.getLogger(__name__)

_COURT_LOCS_CSV = (
    pathlib.Path(__file__).parent.parent.parent
    / "data" / "reference" / "court_locations.csv"
)


def _load_trusted_court_locations() -> dict:
    """Load court_locations.csv into {courtlistener_id: (lat, lng, city, state)}.

    Raises FileNotFoundError if the CSV is missing so that a misconfigured
    Docker image fails loudly rather than silently skipping all court locations.
    """
    result: dict = {}
    if not _COURT_LOCS_CSV.exists():
        raise FileNotFoundError(
            f"Required reference file not found: {_COURT_LOCS_CSV}. "
            "Ensure the Docker image was built with 'COPY data/reference /app/data/reference' "
            "or that the file exists at the expected path."
        )
    with open(_COURT_LOCS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cl_id = (row.get("courtlistener_id") or "").strip()
            if not cl_id:
                continue
            try:
                result[cl_id] = (
                    float(row["latitude"]),
                    float(row["longitude"]),
                    (row.get("city") or "").strip(),
                    (row.get("state_province") or "").strip(),
                )
            except (KeyError, ValueError):
                log.warning("Skipping malformed court_locations row: %r", row)
    return result


_TRUSTED_COURT_LOCS: dict | None = None


def _trusted_court_locs() -> dict:
    """Return the cached court location table, loading on first call."""
    global _TRUSTED_COURT_LOCS
    if _TRUSTED_COURT_LOCS is None:
        _TRUSTED_COURT_LOCS = _load_trusted_court_locations()
    return _TRUSTED_COURT_LOCS

_JURISDICTION_MAP = {
    "FD": "federal_district",
    "FB": "federal_bankruptcy",
    "F": "federal_appellate",
    "FS": "federal_special",
    "S": "state_supreme",
    "SA": "state_appellate",
    "ST": "state_trial",
    "SS": "state_special",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BulkNormalizeResult:
    file_name: str
    rows_read: int = 0
    rows_persisted: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def record_error(self, row_num: int, msg: str) -> None:
        self.errors.append(f"row {row_num}: {msg}")
        self.rows_skipped += 1


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def normalize_courts(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 500,
    run_id: int | None = None,
    source_file: str = "courts",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("courts")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_courts(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_courts(db, batch, result, run_id, source_file, snapshot_date)
    db.flush()
    return result


def normalize_people(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 500,
    run_id: int | None = None,
    source_file: str = "people-db-people",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("people-db-people")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_people(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_people(db, batch, result, run_id, source_file, snapshot_date)
    db.flush()
    return result


def normalize_positions(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 500,
    run_id: int | None = None,
    source_file: str = "people-db-positions",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("people-db-positions")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_positions(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_positions(
            db, batch, result, run_id, source_file, snapshot_date
        )
    db.flush()
    return result


def normalize_dockets(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 500,
    run_id: int | None = None,
    source_file: str = "dockets",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("dockets")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_dockets(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_dockets(
            db, batch, result, run_id, source_file, snapshot_date
        )
    db.flush()
    return result


def normalize_clusters(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 200,
    run_id: int | None = None,
    source_file: str = "opinion-clusters",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("opinion-clusters")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_clusters(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_clusters(
            db, batch, result, run_id, source_file, snapshot_date
        )
    db.flush()
    return result


def normalize_opinions(
    db: Session,
    csv_stream: io.TextIOBase,
    batch_size: int = 500,
    run_id: int | None = None,
    source_file: str = "opinions",
    snapshot_date: str = "",
) -> BulkNormalizeResult:
    result = BulkNormalizeResult("opinions")
    reader = csv.DictReader(csv_stream)
    batch: list[dict] = []
    for row in reader:
        result.rows_read += 1
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_opinions(
                db, batch, result, run_id, source_file, snapshot_date
            )
            batch.clear()
    if batch:
        _flush_opinions(
            db, batch, result, run_id, source_file, snapshot_date
        )
    db.flush()
    return result


# ---------------------------------------------------------------------------
# Flush helpers
# ---------------------------------------------------------------------------

def _write_provenance(
    db: Session,
    run_id: int | None,
    cl_table: str,
    cl_row_id: str,
    source_file: str,
    snapshot_date: str,
    record_type: str,
    record_id: int | None,
) -> None:
    if run_id is None:
        return
    try:
        with db.begin_nested():
            db.add(CLBulkProvenance(
                run_id=run_id,
                cl_table=cl_table,
                cl_row_id=cl_row_id,
                source_file=source_file,
                snapshot_date=snapshot_date,
                record_type=record_type,
                record_id=record_id,
            ))
    except IntegrityError:
        pass


def _flush_courts(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "courts",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        cl_id = _str(row.get("id") or row.get("court_id"))
        if not cl_id:
            result.record_error(result.rows_read - len(rows) + i, "missing id")
            continue
        try:
            existing = db.scalar(
                select(Court).where(Court.courtlistener_id == cl_id)
            )
            if existing:
                result.rows_skipped += 1
                continue
            if cl_id in _trusted_court_locs():
                loc = _get_or_create_court_location(db, cl_id, row)
            else:
                log.debug(
                    "Court %s not in trusted locations — storing as unmapped_court",
                    cl_id,
                )
                loc = _get_or_create_unmapped_court_location(db, cl_id, row)
            prov = {
                "cl_table": "courts",
                "cl_row_id": cl_id,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "run_id": run_id,
            }
            court = Court(
                courtlistener_id=cl_id,
                name=_str(
                    row.get("full_name") or row.get("short_name") or cl_id
                ),
                jurisdiction=_JURISDICTION_MAP.get(
                    _str(row.get("jurisdiction") or ""), None
                ),
                region=_str(row.get("state") or row.get("region")),
                location_id=loc.id,
                cl_provenance=prov,
            )
            db.add(court)
            db.flush()
            _write_provenance(
                db, run_id, "courts", cl_id,
                source_file, snapshot_date, "court", court.id,
            )
            result.rows_persisted += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


def _flush_people(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "people-db-people",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        cl_person_id = _str(row.get("id") or "")
        first = _str(row.get("name_first") or "")
        last = _str(row.get("name_last") or "")
        full = f"{first} {last}".strip()
        if not full:
            result.record_error(
                result.rows_read - len(rows) + i, "missing name"
            )
            continue
        norm = normalize_name(full)
        try:
            # Look up by cl_person_id first (stable), then by normalized name.
            existing: Judge | None = None
            if cl_person_id:
                existing = db.scalar(
                    select(Judge).where(
                        Judge.cl_person_id == cl_person_id
                    )
                )
            if existing is None:
                existing = db.scalar(
                    select(Judge).where(Judge.normalized_name == norm)
                )
            if existing:
                # Backfill cl_person_id if missing
                if cl_person_id and existing.cl_person_id is None:
                    existing.cl_person_id = cl_person_id
                    db.flush()
                result.rows_skipped += 1
                continue
            new_judge = Judge(
                name=full,
                normalized_name=norm,
                court_id=None,
                cl_person_id=cl_person_id or None,
            )
            db.add(new_judge)
            db.flush()
            _write_provenance(
                db, run_id, "people-db-people", cl_person_id or full,
                source_file, snapshot_date, "judge", new_judge.id,
            )
            result.rows_persisted += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


def _flush_positions(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "people-db-positions",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        cl_court_id = _str(row.get("court_id") or "")
        cl_person_id = _str(row.get("person_id") or "")
        if not cl_court_id:
            result.rows_skipped += 1
            continue
        court = db.scalar(
            select(Court).where(Court.courtlistener_id == cl_court_id)
        )
        if not court:
            result.rows_skipped += 1
            continue
        try:
            judge: Judge | None = None
            # Phase 1: look up by CL person ID (stable)
            if cl_person_id:
                judge = db.scalar(
                    select(Judge).where(
                        Judge.cl_person_id == cl_person_id
                    )
                )
            # Phase 2: fallback to normalized name
            if judge is None:
                first = _str(row.get("name_first") or "")
                last = _str(row.get("name_last") or "")
                full = f"{first} {last}".strip()
                if not full:
                    result.rows_skipped += 1
                    continue
                norm = normalize_name(full)
                judge = db.scalar(
                    select(Judge).where(Judge.normalized_name == norm)
                )
            if judge and judge.court_id is None:
                judge.court_id = court.id
                db.flush()
                _write_provenance(
                    db, run_id, "people-db-positions",
                    cl_person_id or _str(row.get("id") or ""),
                    source_file, snapshot_date, "judge", judge.id,
                )
                result.rows_persisted += 1
            else:
                result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


def _flush_dockets(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "dockets",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        cl_court_id = _str(row.get("court_id") or "")
        docket_number = _str(row.get("docket_number") or "")
        if not cl_court_id or not docket_number:
            result.record_error(
                result.rows_read - len(rows) + i,
                "missing court_id or docket_number",
            )
            continue
        court = db.scalar(
            select(Court).where(Court.courtlistener_id == cl_court_id)
        )
        if not court:
            result.record_error(
                result.rows_read - len(rows) + i,
                f"court not found: {cl_court_id}",
            )
            continue
        norm_docket = normalize_docket(docket_number)
        try:
            existing = db.scalar(
                select(Case).where(
                    Case.court_id == court.id,
                    Case.normalized_docket_number == norm_docket,
                )
            )
            if existing:
                result.rows_skipped += 1
                continue
            caption = _str(
                row.get("case_name") or row.get("case_name_short") or docket_number
            )
            docket_cl_id = _str(row.get("id") or "")
            prov = {
                "cl_table": "dockets",
                "cl_row_id": docket_cl_id,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "run_id": run_id,
            }
            new_case = Case(
                court_id=court.id,
                docket_number=docket_number,
                normalized_docket_number=norm_docket,
                caption=caption[:500],
                case_type=_str(row.get("nature_of_suit") or "civil"),
                filed_date=_parse_date(row.get("date_filed")),
                terminated_date=_parse_date(row.get("date_terminated")),
                courtlistener_docket_id=docket_cl_id,
                cl_provenance=prov,
            )
            db.add(new_case)
            db.flush()
            _write_provenance(
                db, run_id, "dockets", docket_cl_id,
                source_file, snapshot_date, "case", new_case.id,
            )
            result.rows_persisted += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


def _flush_clusters(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "opinion-clusters",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        cluster_id = _str(row.get("id") or "")
        docket_id = _str(row.get("docket_id") or row.get("docket") or "")
        if not cluster_id or not docket_id:
            result.record_error(
                result.rows_read - len(rows) + i,
                "missing cluster id or docket_id",
            )
            continue

        case = db.scalar(
            select(Case).where(
                Case.courtlistener_docket_id == docket_id
            )
        )
        if not case:
            result.rows_skipped += 1
            continue

        event_id = f"CL-CLU-{cluster_id}"
        existing = db.scalar(
            select(Event).where(Event.event_id == event_id)
        )
        if existing:
            result.rows_skipped += 1
            continue

        court = db.get(Court, case.court_id)
        if not court:
            result.rows_skipped += 1
            continue

        decision_date = _parse_date(row.get("date_filed"))
        title = _str(
            row.get("case_name") or row.get("case_name_short") or event_id
        )
        summary = _str(row.get("syllabus") or "")
        if not summary:
            summary = f"CourtListener cluster {cluster_id} — {title}"

        try:
            prov = {
                "cl_table": "opinion-clusters",
                "cl_row_id": cluster_id,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "run_id": run_id,
            }
            event = Event(
                event_id=event_id,
                court_id=case.court_id,
                judge_id=None,
                case_id=case.id,
                primary_location_id=court.location_id,
                event_type="published_opinion",
                event_subtype=COURTLISTENER_BULK,
                decision_date=decision_date,
                posted_date=decision_date,
                title=title[:500],
                summary=summary,
                repeat_offender_indicator=False,
                verified_flag=True,
                source_quality="court_record",
                review_status="pending_review",
                public_visibility=False,
                cl_provenance=prov,
                classifier_metadata={
                    "courtlistener_cluster_id": cluster_id,
                    "courtlistener_docket_id": docket_id,
                    "source": COURTLISTENER_BULK,
                },
            )
            db.add(event)
            db.flush()

            # Create LegalSource + EventSource BEFORE the AI check so that
            # _check_event_source can find source_links on the event.
            src_url = (
                f"https://www.courtlistener.com/opinion/{cluster_id}/"
            )
            src_id_str = f"CL-CLU-SRC-{cluster_id}"
            src_hash = url_hash(src_url)
            legal_src = db.scalar(
                select(LegalSource).where(
                    LegalSource.url_hash == src_hash
                )
            )
            if not legal_src:
                legal_src = LegalSource(
                    source_id=src_id_str,
                    source_type="court_record",
                    source_quality="court_record",
                    title=title[:500],
                    url=src_url,
                    url_hash=src_hash,
                    verified_flag=True,
                    retrieved_at=datetime.now(timezone.utc),
                    review_status="pending_review",
                    public_visibility=False,
                    cl_provenance=prov,
                )
                db.add(legal_src)
                db.flush()
            # Link the source to the event
            evt_src = EventSource(
                event_id=event.id,
                source_id=legal_src.id,
                supports_outcome=False,
            )
            db.add(evt_src)
            db.flush()

            # Now run AI correctness — source_links will be populated.
            # Note: Bulk ingestion never auto-publishes. Records remain private
            # and pending_review until human admin review.
            check_court_event(db, event)
            db.flush()
            _write_provenance(
                db, run_id, "opinion-clusters", cluster_id,
                source_file, snapshot_date, "event", event.id,
            )
            result.rows_persisted += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


def _flush_opinions(
    db: Session,
    rows: list[dict],
    result: BulkNormalizeResult,
    run_id: int | None = None,
    source_file: str = "opinions",
    snapshot_date: str = "",
) -> None:
    for i, row in enumerate(rows):
        download_url = _str(row.get("download_url") or row.get("local_path") or "")
        if not download_url:
            result.rows_skipped += 1
            continue
        hashed = url_hash(download_url)
        try:
            existing = db.scalar(
                select(LegalSource).where(LegalSource.url_hash == hashed)
            )
            if existing:
                result.rows_skipped += 1
                continue
            cluster_id = _str(
                row.get("cluster_id") or row.get("opinion_cluster_id") or ""
            )
            opin_cl_id = _str(row.get("id") or uuid4().hex[:10])
            prov = {
                "cl_table": "opinions",
                "cl_row_id": opin_cl_id,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "run_id": run_id,
            }
            new_src = LegalSource(
                source_id=f"CL-OPN-{opin_cl_id}",
                source_type="court_record",
                source_quality="court_record",
                title=f"CourtListener opinion {cluster_id}",
                url=download_url,
                url_hash=hashed,
                verified_flag=True,
                retrieved_at=datetime.now(timezone.utc),
                review_status="pending_review",
                public_visibility=False,
                cl_provenance=prov,
            )
            db.add(new_src)
            db.flush()
            _write_provenance(
                db, run_id, "opinions", opin_cl_id,
                source_file, snapshot_date, "legal_source", new_src.id,
            )
            result.rows_persisted += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
        except Exception as exc:
            db.rollback()
            result.record_error(
                result.rows_read - len(rows) + i, str(exc)
            )


# ---------------------------------------------------------------------------
# Idempotency helpers — CourtListenerBulkRun
# ---------------------------------------------------------------------------

def get_or_create_bulk_run(
    db: Session, snapshot_date: str, file_name: str
) -> CourtListenerBulkRun:
    run = db.scalar(
        select(CourtListenerBulkRun).where(
            CourtListenerBulkRun.snapshot_date == snapshot_date,
            CourtListenerBulkRun.file_name == file_name,
        )
    )
    if not run:
        run = CourtListenerBulkRun(
            snapshot_date=snapshot_date,
            file_name=file_name,
            status=PENDING,
        )
        db.add(run)
        db.flush()
    return run


def mark_run_started(db: Session, run: CourtListenerBulkRun) -> None:
    run.status = RUNNING
    run.started_at = datetime.now(timezone.utc)
    db.flush()


def mark_run_done(
    db: Session,
    run: CourtListenerBulkRun,
    result: BulkNormalizeResult,
) -> None:
    run.status = "done" if not result.errors else "done_with_errors"
    run.rows_read = result.rows_read
    run.rows_persisted = result.rows_persisted
    run.rows_skipped = result.rows_skipped
    run.errors = result.errors[:100]
    run.finished_at = datetime.now(timezone.utc)
    db.flush()


def mark_run_failed(
    db: Session, run: CourtListenerBulkRun, exc: Exception
) -> None:
    run.status = FAILED
    run.errors = [str(exc)]
    run.finished_at = datetime.now(timezone.utc)
    db.flush()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_or_create_unmapped_court_location(
    db: Session, cl_id: str, row: dict
) -> Location:
    """Return or create a placeholder Location for courts without trusted coords.

    Uses location_type='unmapped_court' so public map queries (which filter on
    location_type='courthouse' or non-null coordinates) never expose these dots.
    """
    name = _str(
        row.get("full_name") or row.get("short_name") or f"Court {cl_id}"
    )
    city = _str(row.get("city") or "")
    state = _str(row.get("state") or "")
    existing = db.scalar(
        select(Location).where(
            Location.name == name,
            Location.location_type == "unmapped_court",
        )
    )
    if existing:
        return existing
    loc = Location(
        name=name,
        location_type="unmapped_court",
        city=city,
        state=state,
        latitude=0.0,
        longitude=0.0,
    )
    db.add(loc)
    db.flush()
    return loc


def _get_or_create_court_location(
    db: Session, cl_id: str, row: dict
) -> Location:
    """Return an existing courthouse Location or create a new one.

    Coordinates come exclusively from _trusted_court_locs().
    Callers must verify cl_id is in _trusted_court_locs() before calling.
    """
    lat, lng, trusted_city, trusted_state = _trusted_court_locs()[cl_id]
    city = trusted_city or _str(row.get("city") or "")
    state = trusted_state or _str(row.get("state") or "")
    name = _str(
        row.get("full_name") or row.get("short_name") or f"Court {city}"
    )
    existing = db.scalar(
        select(Location).where(
            Location.name == name,
            Location.location_type == "courthouse",
        )
    )
    if existing:
        return existing
    loc = Location(
        name=name,
        location_type="courthouse",
        city=city,
        state=state,
        latitude=lat,
        longitude=lng,
    )
    db.add(loc)
    db.flush()
    return loc


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    if not raw or raw in ("", "None", "NULL"):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


def _str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()
