"""Unit/integration tests for the Saskatoon CSV → SourceSnapshot → CrimeIncident → ReviewItem pipeline.

These tests verify the provenance wiring introduced in the Phase-1 hardening:
  1. A SourceSnapshot row is created when a CSV batch is imported.
  2. Every new CrimeIncident receives source_snapshot_id pointing to that snapshot.
  3. A ReviewItem is created for each new incident (record_type="crime_incident").
  4. Re-importing the same CSV (idempotent) does not duplicate ReviewItems.
"""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path

import pytest

from app.db.session import SessionLocal
from app.ingestion.crime_sources.saskatoon import import_saskatoon_csv
from app.models.entities import CrimeIncident, ReviewItem, SourceSnapshot

_FIXTURE_CSV = (
    Path(__file__).parent.parent
    / "ingestion"
    / "crime_sources"
    / "fixtures"
    / "saskatoon_sample.csv"
)

_SOURCE_KEY = "saskatoon_crime"
_SOURCE_NAME = "saskatoon_police"


def _read_fixture() -> str:
    return _FIXTURE_CSV.read_text(encoding="utf-8")


def _cleanup(db) -> None:
    """Remove all rows created by the saskatoon fixture so tests stay isolated."""
    # CrimeIncident → SourceSnapshot FK: delete incidents first
    db.query(CrimeIncident).filter(CrimeIncident.source_name == _SOURCE_NAME).delete(
        synchronize_session=False
    )
    db.flush()
    # ReviewItem references source_snapshot; delete before snapshots
    snapshots = (
        db.query(SourceSnapshot).filter(SourceSnapshot.source_key == _SOURCE_KEY).all()
    )
    for snap in snapshots:
        db.query(ReviewItem).filter(ReviewItem.source_snapshot_id == snap.id).delete(
            synchronize_session=False
        )
    db.flush()
    for snap in snapshots:
        db.delete(snap)
    db.commit()


class TestSaskatoonPipelineWiring:
    """Verify SourceSnapshot + ReviewItem wiring in the Saskatoon CSV importer."""

    def setup_method(self) -> None:
        os.environ["JTA_ENABLE_ADMIN_IMPORTS"] = "true"
        os.environ["JTA_LOCAL_FEEDS_ENABLED"] = "true"
        with SessionLocal() as db:
            _cleanup(db)

    def teardown_method(self) -> None:
        os.environ.pop("JTA_ENABLE_ADMIN_IMPORTS", None)
        os.environ.pop("JTA_LOCAL_FEEDS_ENABLED", None)
        with SessionLocal() as db:
            _cleanup(db)

    # ------------------------------------------------------------------
    # Test 1: SourceSnapshot row is created
    # ------------------------------------------------------------------
    def test_snapshot_created_on_csv_import(self) -> None:
        """Importing a CSV must create exactly one SourceSnapshot."""
        csv_text = _read_fixture()
        with SessionLocal() as db:
            result = import_saskatoon_csv(db, StringIO(csv_text))

        assert (
            result.persisted_count > 0
        ), "No incidents persisted; fixture may be broken"

        with SessionLocal() as db:
            count = (
                db.query(SourceSnapshot)
                .filter(SourceSnapshot.source_key == _SOURCE_KEY)
                .count()
            )
        assert count == 1, f"Expected 1 SourceSnapshot, found {count}"

    # ------------------------------------------------------------------
    # Test 2: CrimeIncident rows carry the snapshot FK
    # ------------------------------------------------------------------
    def test_crime_incident_has_snapshot_fk(self) -> None:
        """Every new CrimeIncident must have source_snapshot_id set to the snapshot created for that batch."""
        csv_text = _read_fixture()
        with SessionLocal() as db:
            import_saskatoon_csv(db, StringIO(csv_text))

        with SessionLocal() as db:
            snapshot = (
                db.query(SourceSnapshot)
                .filter(SourceSnapshot.source_key == _SOURCE_KEY)
                .one()
            )
            incidents = (
                db.query(CrimeIncident)
                .filter(CrimeIncident.source_name == _SOURCE_NAME)
                .all()
            )

        assert len(incidents) > 0
        for inc in incidents:
            assert inc.source_snapshot_id == snapshot.id, (
                f"Incident {inc.id} has source_snapshot_id={inc.source_snapshot_id!r}, "
                f"expected {snapshot.id}"
            )

    # ------------------------------------------------------------------
    # Test 3: ReviewItem is created for each new incident
    # ------------------------------------------------------------------
    def test_review_item_created_for_new_incident(self) -> None:
        """Each new CrimeIncident must produce a ReviewItem with record_type='crime_incident'."""
        csv_text = _read_fixture()
        with SessionLocal() as db:
            result = import_saskatoon_csv(db, StringIO(csv_text))

        expected = result.persisted_count

        with SessionLocal() as db:
            snapshot = (
                db.query(SourceSnapshot)
                .filter(SourceSnapshot.source_key == _SOURCE_KEY)
                .one()
            )
            review_count = (
                db.query(ReviewItem)
                .filter(
                    ReviewItem.source_snapshot_id == snapshot.id,
                    ReviewItem.record_type == "crime_incident",
                )
                .count()
            )

        assert (
            review_count == expected
        ), f"Expected {expected} ReviewItem(s), found {review_count}"

    # ------------------------------------------------------------------
    # Test 4: Re-importing the same CSV does not duplicate ReviewItems
    # ------------------------------------------------------------------
    def test_review_item_not_duplicated_on_reimport(self) -> None:
        """Importing the same CSV a second time must not create additional ReviewItems."""
        csv_text = _read_fixture()
        with SessionLocal() as db:
            first = import_saskatoon_csv(db, StringIO(csv_text))

        # Second import of the identical content — incidents already exist, so
        # persist_crime_incident() takes the UPDATE path and is_new=False.
        with SessionLocal() as db:
            second = import_saskatoon_csv(db, StringIO(csv_text))

        with SessionLocal() as db:
            review_count = (
                db.query(ReviewItem)
                .filter(ReviewItem.record_type == "crime_incident")
                .join(
                    SourceSnapshot,
                    ReviewItem.source_snapshot_id == SourceSnapshot.id,
                )
                .filter(SourceSnapshot.source_key == _SOURCE_KEY)
                .count()
            )

        # After two imports, ReviewItems should equal the first import's
        # persisted_count (not doubled).
        assert (
            review_count == first.persisted_count
        ), f"ReviewItems doubled on re-import: expected {first.persisted_count}, got {review_count}"
