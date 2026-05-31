"""Tests for CourtListener bulk provenance writing.

Proves that CLBulkProvenance rows are created when run_id is supplied:
1.  courts    → CLBulkProvenance with cl_table='courts'
2.  people    → CLBulkProvenance with cl_table='people-db-people'
3.  positions → CLBulkProvenance with cl_table='people-db-positions'
4.  dockets   → CLBulkProvenance with cl_table='dockets'
5.  clusters  → CLBulkProvenance with cl_table='opinion-clusters'
6.  opinions  → CLBulkProvenance with cl_table='opinions'
7.  run_id=None → no CLBulkProvenance rows written (safe no-op)
"""
from __future__ import annotations

import io

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
from app.models.entities import CLBulkProvenance, Court, Judge

_SNAP = "2099-06-01"


def _csv(headers: list[str], rows: list[list[str]]) -> io.StringIO:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(f'"{v}"' for v in row))
    return io.StringIO("\n".join(lines))


def _make_run(db, snap: str, stem: str) -> int:
    run = get_or_create_bulk_run(db, snap, stem)
    mark_run_started(db, run)
    db.flush()
    return run.id


# ---------------------------------------------------------------------------
# 1. Courts
# ---------------------------------------------------------------------------

def test_provenance_courts():
    """normalize_courts writes a CLBulkProvenance row for each persisted court."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-courts-01")
        csv_data = _csv(
            ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
            [["prov_test_courts", "Test Court Provenance Courts", "TPRC", "FD", "Test City", "TX"]],
        )
        result = normalize_courts(db, csv_data, run_id=run_id,
                                  source_file="courts", snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted >= 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "courts",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for courts"
        assert rows[0].cl_row_id == "prov_test_courts"
        assert rows[0].record_type == "court"


# ---------------------------------------------------------------------------
# 2. People
# ---------------------------------------------------------------------------

def test_provenance_people():
    """normalize_people writes a CLBulkProvenance row for each persisted judge."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-people-01")
        csv_data = _csv(
            ["id", "name_first", "name_last"],
            [["prov-p-001", "Alice", "ProvJudge"]],
        )
        result = normalize_people(db, csv_data, run_id=run_id,
                                  source_file="people-db-people",
                                  snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted == 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "people-db-people",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for people"
        assert rows[0].record_type == "judge"


# ---------------------------------------------------------------------------
# 3. Positions
# ---------------------------------------------------------------------------

def test_provenance_positions():
    """normalize_positions writes a CLBulkProvenance row when a judge is linked to a court."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-positions-01")
        court_csv = _csv(
            ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
            [["prov_test_pos", "Test Court Provenance Positions", "TPRP", "FD", "Test City", "TX"]],
        )
        people_csv = _csv(
            ["id", "name_first", "name_last"],
            [["prov-pos-p-001", "Bob", "ProvPosition"]],
        )
        positions_csv = _csv(
            ["id", "person_id", "court_id", "name_first", "name_last"],
            [["prov-pos-01", "prov-pos-p-001", "prov_test_pos", "Bob", "ProvPosition"]],
        )
        normalize_courts(db, court_csv)
        normalize_people(db, people_csv)
        result = normalize_positions(db, positions_csv, run_id=run_id,
                                     source_file="people-db-positions",
                                     snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted == 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "people-db-positions",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for positions"
        assert rows[0].record_type == "judge"


# ---------------------------------------------------------------------------
# 4. Dockets
# ---------------------------------------------------------------------------

def test_provenance_dockets():
    """normalize_dockets writes a CLBulkProvenance row for each persisted case."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-dockets-01")
        court_csv = _csv(
            ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
            [["prov_test_dock", "Test Court Provenance Dockets", "TPRD", "FD", "Test City", "TX"]],
        )
        dockets_csv = _csv(
            [
                "id", "court_id", "docket_number", "case_name",
                "date_filed", "date_terminated", "nature_of_suit",
            ],
            [["prov-dock-01", "prov_test_dock", "1:24-cv-0001", "Prov v. Docket",
              "2024-01-01", "", "440"]],
        )
        normalize_courts(db, court_csv)
        result = normalize_dockets(db, dockets_csv, run_id=run_id,
                                   source_file="dockets", snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted >= 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "dockets",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for dockets"
        assert rows[0].record_type == "case"


# ---------------------------------------------------------------------------
# 5. Clusters
# ---------------------------------------------------------------------------

def test_provenance_clusters():
    """normalize_clusters writes a CLBulkProvenance row for each persisted event."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-clusters-01")
        court_csv = _csv(
            ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
            [["prov_test_clus", "Test Court Provenance Clusters", "TPRCL", "FD", "Test City", "TX"]],
        )
        dockets_csv = _csv(
            [
                "id", "court_id", "docket_number", "case_name",
                "date_filed", "date_terminated", "nature_of_suit",
            ],
            [["prov-dock-c01", "prov_test_clus", "2:24-cr-0001", "USA v. ProvCluster",
              "2024-01-01", "", ""]],
        )
        clusters_csv = _csv(
            [
                "id", "docket_id", "date_filed", "case_name",
                "precedential_status", "judges", "nature_of_suit",
            ],
            [["prov-cl-01", "prov-dock-c01", "2024-06-01",
              "USA v. ProvCluster", "Published", "Smith, J.", ""]],
        )
        normalize_courts(db, court_csv)
        normalize_dockets(db, dockets_csv)
        result = normalize_clusters(db, clusters_csv, run_id=run_id,
                                    source_file="opinion-clusters",
                                    snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted >= 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "opinion-clusters",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for clusters"
        assert rows[0].record_type == "event"


# ---------------------------------------------------------------------------
# 6. Opinions
# ---------------------------------------------------------------------------

def test_provenance_opinions():
    """normalize_opinions writes a CLBulkProvenance row for each persisted source."""
    with SessionLocal() as db:
        run_id = _make_run(db, _SNAP, "prov-opinions-01")
        court_csv = _csv(
            ["id", "full_name", "short_name", "jurisdiction", "city", "state"],
            [["prov_test_opin", "Test Court Provenance Opinions", "TPRO", "FD", "Test City", "TX"]],
        )
        dockets_csv = _csv(
            [
                "id", "court_id", "docket_number", "case_name",
                "date_filed", "date_terminated", "nature_of_suit",
            ],
            [["prov-dock-o01", "prov_test_opin", "5:24-cv-0001", "Opinion v. Prov",
              "2024-01-01", "", ""]],
        )
        clusters_csv = _csv(
            [
                "id", "docket_id", "date_filed", "case_name",
                "precedential_status", "judges", "nature_of_suit",
            ],
            [["prov-clus-o01", "prov-dock-o01", "2024-06-01",
              "Opinion v. Prov", "Published", "", ""]],
        )
        opinions_csv = _csv(
            [
                "id", "cluster_id", "type", "download_url",
                "plain_text", "html",
            ],
            [["prov-opin-01", "prov-clus-o01", "010combined",
              "https://storage.courtlistener.com/pdf/prov.pdf", "", ""]],
        )
        normalize_courts(db, court_csv)
        normalize_dockets(db, dockets_csv)
        normalize_clusters(db, clusters_csv)
        result = normalize_opinions(db, opinions_csv, run_id=run_id,
                                    source_file="opinions",
                                    snapshot_date=_SNAP)
        db.commit()

    assert result.rows_persisted >= 1
    with SessionLocal() as db:
        rows = db.scalars(
            select(CLBulkProvenance).where(
                CLBulkProvenance.run_id == run_id,
                CLBulkProvenance.cl_table == "opinions",
            )
        ).all()
        assert len(rows) >= 1, "Expected at least one CLBulkProvenance row for opinions"
        assert rows[0].record_type == "legal_source"


# ---------------------------------------------------------------------------
# 7. run_id=None → no provenance rows written
# ---------------------------------------------------------------------------

def test_provenance_no_run_id_writes_nothing():
    """When run_id is None (legacy call), no CLBulkProvenance rows are written."""
    with SessionLocal() as db:
        before = db.scalar(
            select(CLBulkProvenance).order_by(CLBulkProvenance.id.desc())
        )
        before_id = before.id if before else 0

        csv_data = _csv(
            ["id", "name_first", "name_last"],
            [["prov-noid-001", "NoRun", "ProvTest"]],
        )
        normalize_people(db, csv_data, run_id=None)
        db.commit()

        new_rows = db.scalars(
            select(CLBulkProvenance).where(CLBulkProvenance.id > before_id)
        ).all()
        assert new_rows == [], (
            "Expected zero new CLBulkProvenance rows when run_id is None"
        )
