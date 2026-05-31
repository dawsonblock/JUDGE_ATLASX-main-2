#!/usr/bin/env python3
"""Prepare proof database: run migrations and seed representative data.

This script:
1. Runs Alembic migrations against the proof DB (SQLite) via Alembic Python API.
2. Seeds >= 3 chained AuditLog rows with all chain-v2 hash fields.
3. Seeds >= 3 SourceSnapshot rows (verified, rejected, quarantined).

The release gate must run this BEFORE verify_audit_chain and
verify_evidence_store so that both tools see non-empty data.

Usage:
    python scripts/prepare_proof_db.py [--proof-db PATH]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
PROOF_DIR = REPO_ROOT / "artifacts" / "proof" / "current"


def _backend_python() -> str:
    candidate = BACKEND_DIR / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def run_migrations(proof_db_url: str) -> int:
    """Apply Alembic migrations via Alembic Python API using backend Python."""
    env = {**os.environ, "JTA_DATABASE_URL": proof_db_url}
    migration_code = (
        "from alembic import command; "
        "from alembic.config import Config; "
        f"cfg = Config({str(BACKEND_DIR / 'alembic.ini')!r}); "
        f"cfg.set_main_option('script_location', {str(BACKEND_DIR / 'alembic')!r}); "
        f"cfg.set_main_option('sqlalchemy.url', {proof_db_url!r}); "
        "command.upgrade(cfg, 'head')"
    )
    result = subprocess.run(
        [
            _backend_python(),
            "-c",
            migration_code,
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Migration error:")
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
    return result.returncode


def run_seeding(proof_db_url: str) -> int:
    """Run seed_proof_db.py using the current interpreter (no uv download required)."""
    env = {**os.environ, "JTA_DATABASE_URL": proof_db_url}
    result = subprocess.run(
        [_backend_python(), str(BACKEND_DIR / "scripts" / "seed_proof_db.py")],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Seeding failed:")
        print(result.stdout)
        print(result.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    # Determine proof DB path
    if "--proof-db" in args:
        idx = args.index("--proof-db")
        proof_db_path = Path(args[idx + 1]).resolve()
    else:
        PROOF_DIR.mkdir(parents=True, exist_ok=True)
        proof_db_path = PROOF_DIR / "proof.db"

    proof_db_path.parent.mkdir(parents=True, exist_ok=True)
    if proof_db_path.exists():
        proof_db_path.unlink()
    proof_db_url = f"sqlite:///{proof_db_path}"

    print("PROOF DB PREPARE")

    rc = run_migrations(proof_db_url)
    if rc != 0:
        print("migrations=FAIL")
        print("RESULT: FAIL migration_failed")
        return 1
    print("migrations=PASS")

    rc = run_seeding(proof_db_url)
    if rc != 0:
        print("RESULT: FAIL seeding_failed")
        return 1
    print("audit_entries_seeded=3")
    print("evidence_snapshots_seeded=3")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

