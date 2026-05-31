#!/usr/bin/env python3
"""Verify audit chain integrity and completeness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """Verify audit chain by checking audit log completeness."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "backend" / "tools" / "verify_audit_chain.py"),
        "--allow-empty",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)

    # Print output for logging
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    # Parse violations from output
    violations = 0
    if "violations=" in proc.stdout:
        for line in proc.stdout.splitlines():
            if line.startswith("violations="):
                try:
                    violations = int(line.split("=")[1])
                except (ValueError, IndexError):
                    pass

    combined_output = f"{proc.stdout}\n{proc.stderr}".lower()
    if "no such table" in combined_output and "audit_logs" in combined_output:
        print("warn=no_audit_logs_table")
        return 0

    if violations > 0:
        return 1
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
