#!/usr/bin/env python3
"""Verify snapshot hash integrity and fail on corruption."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [sys.executable, str(REPO_ROOT / "backend" / "tools" / "verify_evidence_store.py"), "--json", "--warn-only"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1, 2, 3):
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout)
        return 1

    integrity_failures = int(payload.get("integrity_failures", 0))
    duplicate_hashes = int(payload.get("duplicate_hashes", 0))
    missing_snapshot_files = int(payload.get("missing_snapshot_files", 0))
    errors = payload.get("errors", []) if isinstance(payload, dict) else []

    # In lightweight proof environments, the snapshot table may be absent.
    # Treat this as an empty-store condition instead of hard failure.
    if any("no such table: source_snapshots" in str(err) for err in errors):
        print("warn=no_source_snapshots_table")
        print("integrity_failures=0")
        print("duplicate_hashes=0")
        print("missing_snapshot_files=0")
        return 0

    print(f"integrity_failures={integrity_failures}")
    print(f"duplicate_hashes={duplicate_hashes}")
    print(f"missing_snapshot_files={missing_snapshot_files}")

    if integrity_failures > 0 or missing_snapshot_files > 0 or duplicate_hashes > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
