#!/usr/bin/env python3
"""Wrapper entrypoint for frontend npm audit triage checks."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "check_npm_audit_triage.py"
    runpy.run_path(str(target), run_name="__main__")
