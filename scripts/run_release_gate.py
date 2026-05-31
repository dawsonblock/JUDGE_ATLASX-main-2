#!/usr/bin/env python3
"""Thin alias for release_gate.py.

Some CI scripts and documentation reference `scripts/run_release_gate.py`.
This file simply delegates to the canonical `scripts/release_gate.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REAL = Path(__file__).resolve().parent / "release_gate.py"

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run([sys.executable, str(_REAL)] + sys.argv[1:]).returncode
    )
