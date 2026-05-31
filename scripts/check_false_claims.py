#!/usr/bin/env python3
"""Compatibility entrypoint for false-claim scanning.

Delegates to scripts/check_truth_claims.py so CI and release checks can use the
new expected filename without duplicating policy logic.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "scripts" / "check_truth_claims.py"
    cmd = [sys.executable, str(target), "--root", str(repo_root)]
    return subprocess.run(cmd, cwd=repo_root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
