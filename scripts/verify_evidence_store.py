#!/usr/bin/env python3
"""Verify evidence store integrity via backend tool wrapper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "backend" / "tools" / "verify_evidence_store.py"),
        *sys.argv[1:],
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
