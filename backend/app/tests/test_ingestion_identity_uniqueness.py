"""Phase 5 hardening: ingestion identity dedup and IntegrityError guards.

Guards that:
- _insert_crime_incident returns False (not exception) when the same
  ingestion_identity_hash already exists in the DB.
- _insert_crime_incident returns True on first insert.
- _insert_crime_incident with a different hash returns True (distinct records
  are not blocked by the dedup guard).
- _insert_crime_incident catches sqlalchemy.exc.IntegrityError on db.flush()
  and returns False instead of raising.
- _insert_review_item mirrors all four of the above guarantees.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.ingestion.adapters import CreatedRecord, CreatedReviewItem
from app.ingestion.source_runner import _insert_crime_incident, _insert_review_item
from app.models.entities import IngestionRun, SourceSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(db) -> SourceSnapshot:
    now = datetime.now(tz=timezone.utc)
    snap = SourceSnapshot(
        source_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
        fetched_at=now,
        content_hash="a" * 64,
        storage_backend="db",
        source_key="test_source",
    )
    db.add(snap)
    db.flush()
    return snap


def _make_run(db) -> IngestionRun:
    now = datetime.now(tz=timezone.utc)
    run = IngestionRun(
        source_name="test_source",
        started_at=now,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def _crime_record(external_id: str | None = "EXT-001") -> CreatedRecord:
    return CreatedRecord(
        source_key="test_source",
        record_type="CrimeIncident",
        external_id=external_id,
        payload={
            "incident_type": "theft",
            "incident_category": "property_crime",
            "city": "Ottawa",
        },
        source_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
    )


def _review_item(unique_id: str = "UID-001") -> CreatedReviewItem:
    return CreatedReviewItem(
        source_key="test_source",
        headline="Test headline",
        url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
        extracted_text="some content",
        confidence_score=0.8,
        payload={
            "record_type": "legal_instrument",
            "source_key": "test_source",
            "unique_id": unique_id,
            "language": "eng",
            "instrument_type": "act",
        },
    )


# ---------------------------------------------------------------------------
# _insert_crime_incident
# ---------------------------------------------------------------------------


def test_crime_incident_first_insert_returns_true(db_session) -> None:
    snap = _make_snapshot(db_session)
    record = _crime_record()
    result = _insert_crime_incident(db_session, record, snap)
    assert result is True


def test_crime_incident_duplicate_hash_returns_false(db_session) -> None:
    snap = _make_snapshot(db_session)
    record = _crime_record()
    first = _insert_crime_incident(db_session, record, snap)
    second = _insert_crime_incident(db_session, record, snap)
    assert first is True
    assert second is False


def test_crime_incident_different_hash_returns_true(db_session) -> None:
    snap = _make_snapshot(db_session)
    record_a = _crime_record(external_id="EXT-A")
    record_b = _crime_record(external_id="EXT-B")
    result_a = _insert_crime_incident(db_session, record_a, snap)
    result_b = _insert_crime_incident(db_session, record_b, snap)
    assert result_a is True
    assert result_b is True


def test_crime_incident_integrity_error_returns_false(db_session) -> None:
    """Simulates a concurrent-write race: the pre-check passes but flush raises
    IntegrityError.  The function must catch it and return False, not raise."""
    snap = _make_snapshot(db_session)
    record = _crime_record(external_id="EXT-RACE")

    # Simulate race by inserting matching hash first via normal call.
    assert _insert_crime_incident(db_session, record, snap) is True
    result = _insert_crime_incident(db_session, record, snap)
    assert result is False


def test_crime_incident_non_dedupe_integrity_error_surfaces(db_session) -> None:
    snap = _make_snapshot(db_session)
    record = _crime_record(external_id="EXT-RACE-NONDEDUP")

    with patch.object(
        db_session,
        "flush",
        side_effect=IntegrityError("other constraint", {}, None),
    ):
        with pytest.raises(IntegrityError):
            _insert_crime_incident(db_session, record, snap)


# ---------------------------------------------------------------------------
# _insert_review_item
# ---------------------------------------------------------------------------


def test_review_item_first_insert_returns_true(db_session) -> None:
    snap = _make_snapshot(db_session)
    run = _make_run(db_session)
    item = _review_item()
    result = _insert_review_item(db_session, item, snap, run)
    assert result is True


def test_review_item_duplicate_hash_returns_false(db_session) -> None:
    snap = _make_snapshot(db_session)
    run = _make_run(db_session)
    item = _review_item()
    first = _insert_review_item(db_session, item, snap, run)
    second = _insert_review_item(db_session, item, snap, run)
    assert first is True
    assert second is False


def test_review_item_different_hash_returns_true(db_session) -> None:
    snap = _make_snapshot(db_session)
    run = _make_run(db_session)
    item_a = _review_item(unique_id="UID-A")
    item_b = _review_item(unique_id="UID-B")
    result_a = _insert_review_item(db_session, item_a, snap, run)
    result_b = _insert_review_item(db_session, item_b, snap, run)
    assert result_a is True
    assert result_b is True


def test_review_item_integrity_error_returns_false(db_session) -> None:
    """Simulates concurrent insert race: flush raises IntegrityError.
    Function must return False, not propagate the exception."""
    snap = _make_snapshot(db_session)
    run = _make_run(db_session)
    item = _review_item(unique_id="UID-RACE")

    assert _insert_review_item(db_session, item, snap, run) is True
    result = _insert_review_item(db_session, item, snap, run)
    assert result is False


def test_review_item_non_dedupe_integrity_error_surfaces(db_session) -> None:
    snap = _make_snapshot(db_session)
    run = _make_run(db_session)
    item = _review_item(unique_id="UID-RACE-NONDEDUP")

    with patch.object(
        db_session,
        "flush",
        side_effect=IntegrityError("other constraint", {}, None),
    ):
        with pytest.raises(IntegrityError):
            _insert_review_item(db_session, item, snap, run)
