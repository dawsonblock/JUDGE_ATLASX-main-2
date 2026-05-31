#!/usr/bin/env python3
"""Proof script: verify the backend app module imports cleanly and has routes.

Exit 0 on success, 1 on failure.
Usage: JTA_APP_ENV=development python scripts/proof_backend_import.py
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Ensure development mode so no missing-secret validation fires.
os.environ.setdefault("JTA_APP_ENV", "development")

print("proof_backend_import: importing app.main ...", flush=True)
try:
    from app.main import app  # noqa: PLC0415
except Exception as exc:
    print(f"FAIL: import raised {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(1)

route_count = len(app.routes)
print(f"proof_backend_import: app has {route_count} routes", flush=True)

if route_count < 1:
    print("FAIL: no routes registered", file=sys.stderr)
    sys.exit(1)

print(f"PASS: backend import OK ({route_count} routes)", flush=True)
sys.exit(0)
