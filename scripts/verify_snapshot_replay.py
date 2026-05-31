#!/usr/bin/env python3
"""Verify SourceSnapshot evidence integrity via hash replay.

For every SourceSnapshot row that has a stored_content_hash, this script
re-computes SHA-256 of the stored payload and compares it to the recorded
hash.  Any mismatch is reported as a tamper/corruption indicator.

Usage:
    python scripts/verify_snapshot_replay.py [--limit N] [--fail-fast]

Exit codes:
    0  All verified snapshots match (or no verifiable rows found).
    1  One or more hash mismatches detected.
    2  Configuration/import error (database unreachable, etc.).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when run from the repo root.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import SourceSnapshot
except ImportError as exc:
    print(f"ERROR: Could not import backend modules: {exc}", file=sys.stderr)
    print(
        "Run this script from the repository root with the backend virtualenv active,\n"
        "or set PYTHONPATH=backend before running.",
        file=sys.stderr,
    )
    sys.exit(2)


def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _check_snapshot(snap: SourceSnapshot) -> list[str]:
    """Return a list of violation strings for the given snapshot (empty = OK)."""
    issues: list[str] = []

    # --- Invariant 1: is_truncated must always be False ---
    if snap.is_truncated:
        issues.append("is_truncated=True (content was stored truncated)")

    # --- Invariant 2: stored_content_hash must equal content_hash ---
    if snap.stored_content_hash is not None:
        if snap.stored_content_hash != snap.content_hash:
            issues.append(
                f"stored_content_hash={snap.stored_content_hash!r} != "
                f"content_hash={snap.content_hash!r}"
            )

    # --- Invariant 3: original_content_hash must equal content_hash ---
    if snap.original_content_hash is not None:
        if snap.original_content_hash != snap.content_hash:
            issues.append(
                f"original_content_hash={snap.original_content_hash!r} != "
                f"content_hash={snap.content_hash!r}"
            )

    # --- Invariant 4: when raw_content is present, SHA-256 must match content_hash ---
    if snap.raw_content is not None:
        computed = _sha256(snap.raw_content)  # _sha256 encodes str→bytes internally
        if computed != snap.content_hash:
            issues.append(
                f"SHA-256(raw_content)={computed!r} != content_hash={snap.content_hash!r}"
            )

    return issues


def verify_snapshots(limit: int | None, fail_fast: bool) -> int:
    """Walk all (or up to *limit*) SourceSnapshot rows and verify evidence invariants.

    Checks (per row):
      1. is_truncated is False
      2. stored_content_hash == content_hash  (when stored_content_hash is set)
      3. original_content_hash == content_hash  (when original_content_hash is set)
      4. SHA-256(raw_content) == content_hash  (when raw_content is present in DB)

    Returns the number of rows with violations.
    """
    violations = 0
    clean = 0

    with SessionLocal() as db:
        stmt = select(SourceSnapshot).order_by(SourceSnapshot.id)
        if limit:
            stmt = stmt.limit(limit)

        rows = list(db.scalars(stmt))

    total = len(rows)
    for snap in rows:
        issues = _check_snapshot(snap)
        if issues:
            violations += 1
            print(
                f"FAIL  id={snap.id}  url={snap.source_url!r}",
                file=sys.stderr,
            )
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            if fail_fast:
                print(
                    f"\nverify_snapshot_replay: stopped at first violation "
                    f"(checked {violations + clean}/{total})",
                    file=sys.stderr,
                )
                return violations
        else:
            clean += 1

    print(
        f"verify_snapshot_replay: total={total}  clean={clean}  violations={violations}"
    )
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of snapshots to check (default: all).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first mismatch.",
    )
    args = parser.parse_args()

    try:
        violations = verify_snapshots(limit=args.limit, fail_fast=args.fail_fast)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
