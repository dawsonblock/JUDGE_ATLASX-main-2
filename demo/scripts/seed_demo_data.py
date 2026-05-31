#!/usr/bin/env python3
"""Seed synthetic demo data into an isolated demo database.

This script does not modify application runtime logic. It writes only synthetic
fixture records used by the local demo package.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
DEMO_ROOT = REPO_ROOT / "demo"
DEMO_DATA_DIR = DEMO_ROOT / "demo_data"
DEMO_DB_PATH = DEMO_ROOT / "demo.sqlite3"


def _ensure_python311() -> None:
    if sys.version_info >= (3, 11):
        return
    candidates = [
        REPO_ROOT / "backend" / ".venv" / "bin" / "python",
        shutil.which("python3.11") and Path(shutil.which("python3.11") or ""),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if candidate_path.exists() and os.access(candidate_path, os.X_OK):
            os.execv(str(candidate_path), [str(candidate_path), *sys.argv])
    raise SystemExit(
        "seed_demo_data.py requires Python 3.11+. "
        "Use backend/.venv/bin/python demo/scripts/seed_demo_data.py"
    )


_ensure_python311()

os.environ.setdefault("JTA_DATABASE_URL", f"sqlite:///{DEMO_DB_PATH}")
os.environ.setdefault("JTA_AUTO_SEED", "false")
os.environ.setdefault("JTA_APP_ENV", "development")

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.actor import AdminActor
from app.auth.admin import log_mutation
from app.db.session import SessionLocal
from app.models.entities import (
    Case,
    CaseParty,
    Court,
    Defendant,
    Event,
    EventDefendant,
    EventSource,
    Judge,
    LegalSource,
    Location,
    ReviewItem,
    SourceRegistry,
    SourceSnapshot,
)
from app.services.linker import url_hash
from app.services.text import normalize_docket, normalize_name


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run_migrations() -> None:
    env = os.environ.copy()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
    )


def _register_sqlite_now(db) -> None:
    if not db.bind or db.bind.dialect.name != "sqlite":
        return
    raw = db.connection().connection
    raw.create_function(
        "now",
        0,
        lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _get_or_create_location(db, name: str, city: str, state: str, lat: float, lon: float) -> Location:
    row = db.query(Location).filter(Location.name == name).first()
    if row:
        return row
    row = Location(
        name=name,
        city=city,
        state=state,
        region="Demo Region",
        latitude=lat,
        longitude=lon,
        location_type="courthouse",
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_court(db, location: Location) -> Court:
    courtlistener_id = "demo-court-001"
    row = db.query(Court).filter(Court.courtlistener_id == courtlistener_id).first()
    if row:
        return row
    row = Court(
        courtlistener_id=courtlistener_id,
        name="DEMO Synthetic District Court",
        jurisdiction="demo",
        region="Demo Region",
        location=location,
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_judge(db, court: Court, judge_name: str) -> Judge:
    normalized = normalize_name(judge_name)
    row = db.query(Judge).filter(Judge.normalized_name == normalized).first()
    if row:
        return row
    row = Judge(name=judge_name, normalized_name=normalized, court=court)
    db.add(row)
    db.flush()
    return row


def _get_or_create_defendant(db, anonymized_id: str, public_name: str) -> Defendant:
    row = db.query(Defendant).filter(Defendant.anonymized_id == anonymized_id).first()
    if row:
        return row
    row = Defendant(
        anonymized_id=anonymized_id,
        public_name=public_name,
        normalized_public_name=normalize_name(public_name),
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_case(db, court: Court, docket_number: str, caption: str) -> Case:
    norm = normalize_docket(docket_number)
    row = (
        db.query(Case)
        .filter(Case.court_id == court.id, Case.normalized_docket_number == norm)
        .first()
    )
    if row:
        return row
    row = Case(
        court=court,
        docket_number=docket_number,
        normalized_docket_number=norm,
        caption=caption,
        case_type="criminal",
        filed_date=date(2025, 1, 1),
        courtlistener_docket_id=f"demo-{norm}",
    )
    db.add(row)
    db.flush()
    return row


def _upsert_source_registry(db, sources_payload: dict) -> int:
    count = 0
    for spec in sources_payload.get("sources", []):
        row = db.query(SourceRegistry).filter(SourceRegistry.source_key == spec["source_key"]).first()
        if row is None:
            row = SourceRegistry(**spec)
            db.add(row)
            count += 1
            continue
        for key, value in spec.items():
            setattr(row, key, value)
    db.flush()
    return count


def _upsert_snapshot(db, item: dict) -> SourceSnapshot:
    existing = db.query(SourceSnapshot).filter(SourceSnapshot.source_url == item["source_url"]).first()
    raw_content = item.get("raw_content") or ""
    extracted_text = item.get("extracted_text") or ""
    hash_value = _sha256_text(raw_content or extracted_text)
    if existing:
        existing.source_key = item["source_key"]
        existing.fetched_at = _parse_datetime(item.get("fetched_at")) or datetime.now(timezone.utc)
        existing.raw_content = raw_content
        existing.extracted_text = extracted_text
        existing.content_hash = hash_value
        existing.original_content_hash = hash_value
        existing.stored_content_hash = hash_value
        existing.content_size_bytes = len(raw_content.encode("utf-8"))
        existing.stored_size_bytes = len(raw_content.encode("utf-8"))
        existing.http_status = item.get("http_status")
        existing.content_type = item.get("content_type")
        existing.is_truncated = False
        return existing
    row = SourceSnapshot(
        source_key=item["source_key"],
        source_url=item["source_url"],
        fetched_at=_parse_datetime(item.get("fetched_at")) or datetime.now(timezone.utc),
        content_hash=hash_value,
        original_content_hash=hash_value,
        stored_content_hash=hash_value,
        raw_content=raw_content,
        extracted_text=extracted_text,
        http_status=item.get("http_status"),
        content_type=item.get("content_type"),
        storage_backend="db",
        content_size_bytes=len(raw_content.encode("utf-8")),
        stored_size_bytes=len(raw_content.encode("utf-8")),
        is_truncated=False,
    )
    db.add(row)
    db.flush()
    return row


def _upsert_review_item(db, item: dict, snapshot_map: dict[str, SourceSnapshot]) -> None:
    source_url = item["source_url"]
    row = db.query(ReviewItem).filter(ReviewItem.source_url == source_url).first()
    snapshot = snapshot_map[item["source_snapshot_key"]]
    payload = item["suggested_payload_json"]
    if row is None:
        row = ReviewItem(
            record_type=item["record_type"],
            source_snapshot_id=snapshot.id,
            suggested_payload_json=payload,
            source_url=source_url,
            source_quality=item["source_quality"],
            confidence=float(item["confidence"]),
            privacy_status=item["privacy_status"],
            publish_recommendation=item["publish_recommendation"],
            public_visibility=bool(item["public_visibility"]),
            status=item["status"],
            reviewer_id=item.get("reviewer_id"),
            reviewer_notes=item.get("reviewer_notes"),
            reviewed_at=datetime.now(timezone.utc) if item["status"] in {"approved", "published", "rejected"} else None,
        )
        db.add(row)
        db.flush()
        return
    row.source_snapshot_id = snapshot.id
    row.suggested_payload_json = payload
    row.source_quality = item["source_quality"]
    row.confidence = float(item["confidence"])
    row.privacy_status = item["privacy_status"]
    row.publish_recommendation = item["publish_recommendation"]
    row.public_visibility = bool(item["public_visibility"])
    row.status = item["status"]
    row.reviewer_id = item.get("reviewer_id")
    row.reviewer_notes = item.get("reviewer_notes")


def _upsert_event_bundle(db, event_item: dict, court: Court, location: Location) -> None:
    judge = _get_or_create_judge(db, court, event_item["judge_name"])
    case = _get_or_create_case(db, court, event_item["docket_number"], event_item["caption"])
    defendant = _get_or_create_defendant(
        db,
        event_item["defendant_anonymized_id"],
        event_item["defendant_public_name"],
    )

    party = (
        db.query(CaseParty)
        .filter(
            CaseParty.case_id == case.id,
            CaseParty.defendant_id == defendant.id,
            CaseParty.party_type == "defendant",
        )
        .first()
    )
    if party is None:
        db.add(
            CaseParty(
                case_id=case.id,
                defendant_id=defendant.id,
                party_type="defendant",
                public_name=defendant.public_name,
                normalized_name=normalize_name(defendant.public_name or defendant.anonymized_id),
            )
        )
        db.flush()

    event = db.query(Event).filter(Event.event_id == event_item["event_id"]).first()
    if event is None:
        event = Event(
            event_id=event_item["event_id"],
            court_id=court.id,
            judge_id=judge.id,
            case_id=case.id,
            primary_location_id=location.id,
            event_type=event_item["event_type"],
            event_subtype=None,
            decision_result=event_item.get("decision_result"),
            decision_date=_parse_date(event_item.get("decision_date")),
            posted_date=_parse_date(event_item.get("posted_date")),
            title=event_item["title"],
            summary=event_item["summary"],
            repeat_offender_indicator=False,
            verified_flag=bool(event_item.get("verified_flag", False)),
            source_quality=event_item.get("source_quality", "court_record"),
            last_verified_at=datetime.now(timezone.utc) if event_item.get("verified_flag") else None,
            review_status=event_item["review_status"],
            public_visibility=bool(event_item["public_visibility"]),
            reviewed_at=datetime.now(timezone.utc) if event_item["public_visibility"] else None,
            reviewed_by="demo-reviewer" if event_item["public_visibility"] else None,
            review_notes="Synthetic demo fixture.",
        )
        db.add(event)
        db.flush()
    else:
        event.review_status = event_item["review_status"]
        event.public_visibility = bool(event_item["public_visibility"])
        event.verified_flag = bool(event_item.get("verified_flag", False))
        event.title = event_item["title"]
        event.summary = event_item["summary"]
        event.source_quality = event_item.get("source_quality", "court_record")
        event.decision_result = event_item.get("decision_result")
        event.decision_date = _parse_date(event_item.get("decision_date"))
        event.posted_date = _parse_date(event_item.get("posted_date"))

    link = (
        db.query(EventDefendant)
        .filter(EventDefendant.event_id == event.id, EventDefendant.defendant_id == defendant.id)
        .first()
    )
    if link is None:
        db.add(EventDefendant(event_id=event.id, defendant_id=defendant.id))
        db.flush()

    source_url = f"https://demo.local/event/{event.event_id}"
    source = db.query(LegalSource).filter(LegalSource.source_id == f"SRC-{event.event_id}").first()
    if source is None:
        source = LegalSource(
            source_id=f"SRC-{event.event_id}",
            source_type="court_record",
            title=f"DEMO source for {event.event_id}",
            url=source_url,
            url_hash=url_hash(source_url),
            source_quality="court_record",
            verified_flag=bool(event.public_visibility),
            retrieved_at=datetime.now(timezone.utc),
            review_status=event.review_status,
            public_visibility=bool(event.public_visibility),
        )
        db.add(source)
        db.flush()

    event_source = (
        db.query(EventSource)
        .filter(EventSource.event_id == event.id, EventSource.source_id == source.id)
        .first()
    )
    if event_source is None:
        db.add(EventSource(event_id=event.id, source_id=source.id, supports_outcome=True))


def main() -> int:
    _run_migrations()

    sources_payload = _load_yaml(DEMO_DATA_DIR / "sources.demo.yaml")
    public_events = _load_json(DEMO_DATA_DIR / "public_events.demo.json")
    private_events = _load_json(DEMO_DATA_DIR / "private_events.demo.json")
    snapshots = _load_json(DEMO_DATA_DIR / "evidence_snapshots.demo.json")
    review_items = _load_json(DEMO_DATA_DIR / "review_items.demo.json")

    actor = AdminActor(
        actor_id="demo-seed-script",
        actor_type="service",
        role="admin",
        auth_method="service",
    )

    with SessionLocal() as db:
        _register_sqlite_now(db)
        source_count = _upsert_source_registry(db, sources_payload)
        location = _get_or_create_location(
            db,
            name="DEMO Synthetic Federal Courthouse",
            city="DemoCity",
            state="DS",
            lat=44.1234,
            lon=-93.1234,
        )
        court = _get_or_create_court(db, location)

        snapshot_map: dict[str, SourceSnapshot] = {}
        for item in snapshots:
            snapshot_map[item["snapshot_key"]] = _upsert_snapshot(db, item)

        for item in review_items:
            _upsert_review_item(db, item, snapshot_map)

        for event_item in public_events + private_events:
            _upsert_event_bundle(db, event_item, court, location)

        log_mutation(
            action="demo_seed_data",
            entity_type="demo",
            entity_id="demo-package",
            payload={
                "source_count": len(sources_payload.get("sources", [])),
                "public_events": len(public_events),
                "private_events": len(private_events),
                "snapshots": len(snapshots),
                "review_items": len(review_items),
            },
            actor=actor,
            db=db,
            fail_closed=True,
        )

        db.commit()

    print("Demo data seeded successfully.")
    print(f"Database: {os.environ.get('JTA_DATABASE_URL')}")
    print(f"Sources upserted: {len(sources_payload.get('sources', []))} (new: {source_count})")
    print(f"Public events fixture rows: {len(public_events)}")
    print(f"Private events fixture rows: {len(private_events)}")
    print(f"Evidence snapshots fixture rows: {len(snapshots)}")
    print(f"Review items fixture rows: {len(review_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
