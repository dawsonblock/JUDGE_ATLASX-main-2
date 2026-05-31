"""Verify evidence snapshot integrity, duplicates, and orphaned artifacts.

Usage:
    python -m backend.tools.verify_evidence_store [--json] [--allow-empty] [--warn-only]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

# Ensure the backend directory is importable as top-level `app` when running
# `python -m backend.tools.*` from repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402  # type: ignore[import-not-found]
from app.models.entities import (  # noqa: E402  # type: ignore[import-not-found]
    SourceSnapshot,
)
from app.services.evidence_integrity import (  # noqa: E402  # type: ignore[import-not-found]
    verify_all_recent_snapshots,
)


def _collect_store_paths() -> set[Path]:
    """Collect filesystem evidence paths under configured store roots."""
    roots: list[Path] = []
    env_root = os.getenv("JTA_EVIDENCE_STORE_ROOT")
    if env_root:
        roots.append(Path(env_root))
    roots.append((BACKEND_DIR / "artifacts" / "evidence").resolve())

    files: set[Path] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                files.add(p.resolve())
    return files


def _emit(result: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print("EVIDENCE STORE VERIFICATION")
    print(f"snapshots_checked={result['snapshots_checked']}")
    print(f"verified_snapshots={result['verified_snapshots']}")
    print(f"integrity_failures={result['integrity_failures']}")
    print(f"corrupt_snapshots={result['corrupt_snapshots']}")
    print(f"duplicate_hashes={result['duplicate_hashes']}")
    print(f"missing_snapshot_files={result['missing_snapshot_files']}")
    print(f"orphan_files={result['orphan_files']}")
    print(f"orphan_snapshot_rows={result['orphan_snapshot_rows']}")
    print(f"rejected_or_quarantined_count={result['rejected_or_quarantined_count']}")
    integrity_errors = [e for e in result.get("errors", []) if e.startswith("integrity_mismatch")]
    if integrity_errors:
        print("Integrity mismatches:")
        for e in integrity_errors:
            print(f"  {e}")
    dup_errors = [e for e in result.get("errors", []) if e.startswith("duplicate_hash")]
    if dup_errors:
        print("Duplicate content_hash entries:")
        for e in dup_errors:
            print(f"  {e}")
    print(f"RESULT: {result['status']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify evidence store integrity")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Return exit 0 even when warnings are present",
    )
    args = parser.parse_args(argv if argv is not None else [])

    try:
        with SessionLocal() as db:
            snapshots = db.scalars(
                select(SourceSnapshot).order_by(SourceSnapshot.id)
            ).all()
            if not snapshots:
                result = {
                    "status": "PASS" if args.allow_empty else "FAIL",
                    "snapshots_checked": 0,
                    "verified_snapshots": 0,
                    "integrity_failures": 0 if args.allow_empty else 1,
                    "corrupt_snapshots": 0,
                    "duplicate_hashes": 0,
                    "missing_snapshot_files": 0,
                    "orphan_files": 0,
                    "orphan_snapshot_rows": 0,
                    "rejected_or_quarantined_count": 0,
                    "warnings": [] if args.allow_empty else ["empty_evidence_store"],
                    "errors": [] if args.allow_empty else ["empty_evidence_store"],
                }
                _emit(result, args.json)
                return 0 if args.allow_empty else 1
            results = verify_all_recent_snapshots(db, limit=len(snapshots))
    except SQLAlchemyError as exc:
        if args.allow_empty and "no such table" in str(exc).lower():
            result = {
                "status": "PASS",
                "snapshots_checked": 0,
                "verified_snapshots": 0,
                "integrity_failures": 0,
                "corrupt_snapshots": 0,
                "duplicate_hashes": 0,
                "missing_snapshot_files": 0,
                "orphan_files": 0,
                "orphan_snapshot_rows": 0,
                "rejected_or_quarantined_count": 0,
                "warnings": ["empty_evidence_store"],
                "errors": [],
            }
            _emit(result, args.json)
            return 0
        result = {
            "status": "FAIL",
            "snapshots_checked": 0,
            "verified_snapshots": 0,
            "integrity_failures": 1,
            "corrupt_snapshots": 0,
            "duplicate_hashes": 0,
            "missing_snapshot_files": 0,
            "orphan_files": 0,
            "orphan_snapshot_rows": 0,
            "rejected_or_quarantined_count": 0,
            "warnings": [],
            "errors": [f"database_error={exc.__class__.__name__}: {exc}"],
        }
        _emit(result, args.json)
        return 3

    failed = [r for r in results if not r.ok]

    hashes = [s.content_hash for s in snapshots if s.content_hash]
    dup_counts = Counter(hashes)
    duplicates = {h: c for h, c in dup_counts.items() if c > 1}
    verified = len(results) - len(failed)

    snapshot_paths: set[Path] = set()
    missing_snapshot_files: list[int] = []
    for snapshot in snapshots:
        sp = getattr(snapshot, "storage_path", None)
        if sp:
            p = Path(sp).expanduser()
            if not p.is_absolute():
                p = (BACKEND_DIR / p).resolve()
            snapshot_paths.add(p)
            if not p.exists():
                missing_snapshot_files.append(getattr(snapshot, "id", None))

    store_paths = _collect_store_paths()
    orphan_files = [str(p) for p in sorted(store_paths - snapshot_paths)]
    orphan_snapshot_rows = [
        getattr(snapshot, "id", None)
        for snapshot in snapshots
        if getattr(snapshot, "storage_backend", "db") != "db"
        and not getattr(snapshot, "storage_path", None)
    ]

    errors: list[str] = []
    warnings: list[str] = []
    if failed:
        errors.extend([
            f"integrity_mismatch snapshot_id={r.snapshot_id} error={r.error_message}"
            for r in failed
        ])
    if duplicates:
        errors.extend([
            f"duplicate_hash hash={h} count={c}"
            for h, c in sorted(duplicates.items())
        ])
    if missing_snapshot_files:
        errors.extend([f"missing_snapshot_file snapshot_id={sid}" for sid in missing_snapshot_files])
    if orphan_snapshot_rows:
        errors.extend([f"orphan_snapshot_row snapshot_id={sid}" for sid in orphan_snapshot_rows])
    if orphan_files:
        warnings.extend([f"orphan_file path={path}" for path in orphan_files[:25]])

    has_error = bool(errors)
    has_warning = bool(warnings)

    status = "PASS"
    if has_error:
        status = "FAIL"
    elif has_warning:
        status = "WARN"

    result = {
        "status": status,
        "snapshots_checked": len(results),
        "verified_snapshots": verified,
        "integrity_failures": len(failed),
        "corrupt_snapshots": len(failed),
        "duplicate_hashes": len(duplicates),
        "missing_snapshot_files": len(missing_snapshot_files),
        "orphan_files": len(orphan_files),
        "orphan_snapshot_rows": len(orphan_snapshot_rows),
        "rejected_or_quarantined_count": 0,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "missing": len(missing_snapshot_files),
            "corrupt": len(failed),
            "orphans": len(orphan_files) + len(orphan_snapshot_rows),
        },
    }
    _emit(result, args.json)

    if has_error:
        return 1
    if has_warning and not args.warn_only:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
