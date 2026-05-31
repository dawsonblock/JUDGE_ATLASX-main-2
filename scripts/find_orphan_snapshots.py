#!/usr/bin/env python3
"""Report orphaned evidence snapshot files and rows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [sys.executable, str(REPO_ROOT / "backend" / "tools" / "verify_evidence_store.py"), "--json", "--warn-only"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1, 2):
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout)
        return 1

    orphan_files = int(payload.get("orphan_files", 0))
    orphan_rows = int(payload.get("orphan_snapshot_rows", 0))

    print(f"orphan_files={orphan_files}")
    print(f"orphan_snapshot_rows={orphan_rows}")

    # Fail if any orphan snapshot rows exist. Orphan files are warnings.
    return 1 if orphan_rows > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
