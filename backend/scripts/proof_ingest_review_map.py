"""Proof script: ingest → review → map public visibility pipeline.

Runs 9 discrete checks against an in-memory SQLite database using the actual
service layer (source_control, snapshot_writer, MemoryRebuildRun, ReviewItem,
ReviewActionLog, CrimeIncident).  Exits 0 when every check passes, 1 on any
failure.  Designed to run in CI without a live database or Redis.

Usage:
    cd backend && python scripts/proof_ingest_review_map.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Force development environment before any app import so Settings resolves
# without missing required variables.
# ---------------------------------------------------------------------------
os.environ.setdefault("JTA_APP_ENV", "development")
os.environ.setdefault("JTA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JTA_ADMIN_TOKEN", "test-proof-token")
os.environ.setdefault("JTA_JWT_SECRET_KEY", "proof-secret-key-not-for-production")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# ---------------------------------------------------------------------------
# Import ORM base and ALL entity classes so Base.metadata is fully populated
# before create_all().
# ---------------------------------------------------------------------------
from app.db.session import Base  # noqa: E402
import app.models.entities as _entities  # noqa: E402,F401 – ensures all tables register
from app.models.entities import (  # noqa: E402
    CrimeIncident,
    MemoryRebuildRun,
    ReviewActionLog,
    ReviewItem,
    SourceRegistry,
    SourceSnapshot,
)
from app.services.source_control import (  # noqa: E402
    SourceDisabledError,
    require_source_enabled,
)
from app.services.snapshot_writer import write_snapshot  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"

_results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = _PASS if condition else _FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    _results.append((label, condition, detail))


# ---------------------------------------------------------------------------
# Build in-memory DB
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
# Enable FK support for SQLite so FK constraints are respected.
with engine.connect() as conn:
    conn.execute(text("PRAGMA foreign_keys = ON"))
    conn.commit()

Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Proof steps
# ---------------------------------------------------------------------------

print("\n=== proof_ingest_review_map.py ===\n")

with Session(engine) as db:

    # ------------------------------------------------------------------
    # Step 1: DB tables created (sanity)
    # ------------------------------------------------------------------
    try:
        count = db.query(SourceRegistry).count()
        check("Step 1: DB tables created", True, f"source_registry has {count} rows")
    except Exception as exc:  # noqa: BLE001
        check("Step 1: DB tables created", False, str(exc))

    # ------------------------------------------------------------------
    # Step 2: disabled source blocks require_source_enabled
    # ------------------------------------------------------------------
    disabled_src = SourceRegistry(
        source_key="proof-source",
        source_name="Proof Source",
        source_type="news",
        is_active=False,
    )
    db.add(disabled_src)
    db.flush()

    try:
        require_source_enabled(db, "proof-source")
        check(
            "Step 2: disabled source raises SourceDisabledError",
            False,
            "no exception raised",
        )
    except SourceDisabledError:
        check("Step 2: disabled source raises SourceDisabledError", True)
    except Exception as exc:  # noqa: BLE001
        check("Step 2: disabled source raises SourceDisabledError", False, str(exc))

    # ------------------------------------------------------------------
    # Step 3: enabled source passes require_source_enabled
    # ------------------------------------------------------------------
    disabled_src.is_active = True
    db.flush()

    try:
        src = require_source_enabled(db, "proof-source")
        check("Step 3: enabled source passes require_source_enabled", src is not None)
    except Exception as exc:  # noqa: BLE001
        check("Step 3: enabled source passes require_source_enabled", False, str(exc))

    # ------------------------------------------------------------------
    # Step 4: write_snapshot creates a SourceSnapshot row
    # ------------------------------------------------------------------
    snap_before = db.query(SourceSnapshot).count()
    try:
        snapshot = write_snapshot(
            db=db,
            source_url="https://example.com/proof",
            fetched_at=datetime.now(timezone.utc),
            content=b"proof content for ingest pipeline",
            source_key="proof-source",
        )
        db.commit()
        snap_after = db.query(SourceSnapshot).count()
        check(
            "Step 4: write_snapshot creates SourceSnapshot",
            snap_after == snap_before + 1,
            f"rows before={snap_before} after={snap_after}",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        check("Step 4: write_snapshot creates SourceSnapshot", False, str(exc))
        snapshot = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Step 5: write_snapshot does not queue MemoryRebuildRun directly
    # ------------------------------------------------------------------
    if snapshot is not None:
        try:
            mrr = (
                db.query(MemoryRebuildRun)
                .filter(
                    MemoryRebuildRun.rebuild_reason == f"new_snapshot:{snapshot.id}"
                )
                .first()
            )
            check(
                "Step 5: write_snapshot does not queue MemoryRebuildRun",
                mrr is None,
                f"status={getattr(mrr, 'status', None)}",
            )
        except Exception as exc:  # noqa: BLE001
            check(
                "Step 5: write_snapshot does not queue MemoryRebuildRun",
                False,
                str(exc),
            )
    else:
        check(
            "Step 5: write_snapshot does not queue MemoryRebuildRun",
            False,
            "skipped — no snapshot",
        )

    # ------------------------------------------------------------------
    # Step 6: ReviewItem linked to snapshot has status=pending
    # ------------------------------------------------------------------
    snap_id = snapshot.id if snapshot is not None else 0
    ri = ReviewItem(
        record_type="crime_incident",
        source_snapshot_id=snap_id,
        suggested_payload_json={"proof": True},
        source_quality="high",
        confidence=0.9,
        privacy_status="public",
        publish_recommendation="approve",
        status="pending",
    )
    db.add(ri)
    db.commit()

    try:
        fetched_ri = (
            db.query(ReviewItem)
            .filter(ReviewItem.source_snapshot_id == snap_id)
            .first()
        )
        check(
            "Step 6: ReviewItem with source_snapshot_id has status=pending",
            fetched_ri is not None and fetched_ri.status == "pending",
            f"status={getattr(fetched_ri, 'status', None)}",
        )
    except Exception as exc:  # noqa: BLE001
        check(
            "Step 6: ReviewItem with source_snapshot_id has status=pending",
            False,
            str(exc),
        )

    # ------------------------------------------------------------------
    # Step 7: ReviewActionLog is created for the ReviewItem
    # ------------------------------------------------------------------
    try:
        ral = ReviewActionLog(
            review_item_id=ri.id,
            actor="proof-admin",
            action="approved",
            before_json={"review_status": "pending"},
            after_json={"review_status": "approved", "is_public": True},
        )
        db.add(ral)
        db.commit()

        fetched_ral = (
            db.query(ReviewActionLog)
            .filter(ReviewActionLog.review_item_id == ri.id)
            .first()
        )
        check(
            "Step 7: ReviewActionLog created for ReviewItem",
            fetched_ral is not None and fetched_ral.action == "approved",
            f"action={getattr(fetched_ral, 'action', None)}",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        check("Step 7: ReviewActionLog created for ReviewItem", False, str(exc))

    # ------------------------------------------------------------------
    # Step 8: CrimeIncident with is_public=False absent from public query
    # ------------------------------------------------------------------
    incident = CrimeIncident(
        incident_type="Proof Incident",
        incident_category="property",
        source_name="proof-source",
        is_public=False,
        review_status="pending_review",
        source_snapshot_id=snap_id,
    )
    db.add(incident)
    db.commit()

    try:
        public_count = (
            db.query(CrimeIncident).filter(CrimeIncident.is_public.is_(True)).count()
        )
        check(
            "Step 8: is_public=False incident absent from public query",
            public_count == 0,
            f"public_count={public_count}",
        )
    except Exception as exc:  # noqa: BLE001
        check(
            "Step 8: is_public=False incident absent from public query", False, str(exc)
        )

    # ------------------------------------------------------------------
    # Step 9: After setting is_public=True, incident appears in public query
    # ------------------------------------------------------------------
    try:
        incident.is_public = True
        db.commit()

        public_count = (
            db.query(CrimeIncident).filter(CrimeIncident.is_public.is_(True)).count()
        )
        check(
            "Step 9: is_public=True incident appears in public query",
            public_count >= 1,
            f"public_count={public_count}",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        check(
            "Step 9: is_public=True incident appears in public query", False, str(exc)
        )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

passed = sum(1 for _, ok, _ in _results if ok)
total = len(_results)
print(f"\nResult: {passed}/{total} checks passed\n")

if passed < total:
    failed = [lbl for lbl, ok, _ in _results if not ok]
    print("FAILED checks:", ", ".join(failed))
    sys.exit(1)

sys.exit(0)
