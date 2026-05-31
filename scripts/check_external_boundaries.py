#!/usr/bin/env python3
"""Compatibility entrypoint for external-boundary checks.

Delegates to backend/scripts/check_repo_boundaries.py and preserves its exit
status so this script can be used directly in CI and release gating.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "backend" / "scripts" / "check_repo_boundaries.py"
    cmd = [sys.executable, str(target)]
    return subprocess.run(cmd, cwd=repo_root / "backend").returncode


if __name__ == "__main__":
    raise SystemExit(main())
