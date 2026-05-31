#!/usr/bin/env python3
"""Import CourtListener bulk-data CSVs into JudgeTracker.

Usage:
    python scripts/import_courtlistener_bulk.py --date 2026-03-31
    python scripts/import_courtlistener_bulk.py --date 2026-03-31 --force
    python scripts/import_courtlistener_bulk.py --date 2026-03-31 --files courts,dockets
    python scripts/import_courtlistener_bulk.py --date 2026-03-31 --include-opinions

Run from the repo root. Expects CSVs at:
    data/courtlistener-bulk/<stem>-YYYY-MM-DD.csv

The normalizer streams rows in batches — no staging DB required.
Idempotency: same (date, file) cannot be re-imported unless --force.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.courtlistener_bulk_normalizer import (
    BulkNormalizeResult,
    get_or_create_bulk_run,
    mark_run_done,
    mark_run_failed,
    mark_run_started,
    normalize_clusters,
    normalize_courts,
    normalize_dockets,
    normalize_opinions,
    normalize_people,
    normalize_positions,
)
from app.models.entities import CourtListenerBulkRun

ORDERED_FILES = [
    "courts",
    "people-db-people",
    "people-db-positions",
    "dockets",
    "opinion-clusters",
]

NORMALIZERS = {
    "courts": normalize_courts,
    "people-db-people": normalize_people,
    "people-db-positions": normalize_positions,
    "dockets": normalize_dockets,
    "opinion-clusters": normalize_clusters,
    "opinions": normalize_opinions,
}


def find_csv(data_dir: str, stem: str, date: str) -> str | None:
    candidate = os.path.join(data_dir, f"{stem}-{date}.csv")
    if os.path.exists(candidate):
        return candidate
    for fname in sorted(os.listdir(data_dir)):
        if fname.startswith(stem) and fname.endswith(".csv"):
            return os.path.join(data_dir, fname)
    return None


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Import CourtListener bulk CSVs"
    )
    parser.add_argument(
        "--date",
        default=settings.courtlistener_bulk_snapshot_date,
        help="Snapshot date YYYY-MM-DD",
    )
    parser.add_argument(
        "--data-dir",
        default=settings.courtlistener_bulk_data_dir,
        help="Directory with downloaded CSVs",
    )
    parser.add_argument(
        "--files",
        default=None,
        help="Comma-separated file stems to import (default: all enabled)",
    )
    parser.add_argument(
        "--include-opinions",
        action="store_true",
        default=settings.courtlistener_bulk_include_opinions,
        help="Also import opinions CSV (large)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-import even if already done",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.courtlistener_bulk_import_batch_size,
    )
    args = parser.parse_args()

    if not args.date:
        print(
            "ERROR: --date required or set JTA_COURTLISTENER_BULK_SNAPSHOT_DATE",
            file=sys.stderr,
        )
        sys.exit(1)

    enabled_stems = (
        [s.strip() for s in args.files.split(",")]
        if args.files
        else [
            s.strip()
            for s in settings.courtlistener_bulk_enabled_files.split(",")
        ]
    )
    if args.include_opinions and "opinions" not in enabled_stems:
        enabled_stems.append("opinions")

    ordered = [s for s in ORDERED_FILES if s in enabled_stems]
    if args.include_opinions and "opinions" not in ordered:
        ordered.append("opinions")

    print(f"Snapshot date : {args.date}")
    print(f"Data dir      : {args.data_dir}")
    print(f"Files         : {ordered}")
    print(f"Force         : {args.force}")
    print()

    for stem in ordered:
        csv_path = find_csv(args.data_dir, stem, args.date)
        if not csv_path:
            print(f"  SKIP {stem}: file not found in {args.data_dir}")
            continue

        with SessionLocal() as db:
            run = get_or_create_bulk_run(db, args.date, stem)
            if run.status in ("done", "done_with_errors") and not args.force:
                print(
                    f"  SKIP {stem}: already imported "
                    f"({run.rows_persisted} rows). Use --force to re-import."
                )
                db.commit()
                continue

            if args.force and run.status != "pending":
                db.delete(run)
                db.flush()
                run = get_or_create_bulk_run(db, args.date, stem)

            mark_run_started(db, run)
            db.commit()

        print(f"  IMPORTING {stem} from {csv_path} ...")
        try:
            with SessionLocal() as db:
                run = db.get(
                    CourtListenerBulkRun,
                    db.scalars(
                        __import__("sqlalchemy").select(
                            CourtListenerBulkRun.id
                        ).where(
                            CourtListenerBulkRun.snapshot_date == args.date,
                            CourtListenerBulkRun.file_name == stem,
                        )
                    ).first(),
                )
                with open(csv_path, encoding="utf-8", errors="replace") as fh:
                    normalizer_fn = NORMALIZERS[stem]
                    result: BulkNormalizeResult = normalizer_fn(
                        db, fh, args.batch_size, run.id, stem, args.date
                    )
                mark_run_done(db, run, result)
                db.commit()
            print(
                f"    read={result.rows_read}  "
                f"persisted={result.rows_persisted}  "
                f"skipped={result.rows_skipped}  "
                f"errors={len(result.errors)}"
            )
            if result.errors:
                for err in result.errors[:5]:
                    print(f"    ! {err}")
                if len(result.errors) > 5:
                    print(f"    ... and {len(result.errors) - 5} more")
        except Exception as exc:
            with SessionLocal() as db:
                run = db.scalars(
                    __import__("sqlalchemy").select(CourtListenerBulkRun).where(
                        CourtListenerBulkRun.snapshot_date == args.date,
                        CourtListenerBulkRun.file_name == stem,
                    )
                ).first()
                if run:
                    mark_run_failed(db, run, exc)
                    db.commit()
            print(f"  FAILED {stem}: {exc}", file=sys.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
