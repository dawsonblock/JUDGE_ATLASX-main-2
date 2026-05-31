#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DB_PATH="${ROOT_DIR}/demo/demo.sqlite3"
export JTA_DATABASE_URL="${JTA_DATABASE_URL:-sqlite:///${DEMO_DB_PATH}}"
DEMO_BACKEND_PORT="${DEMO_BACKEND_PORT:-8010}"
API_BASE="${DEMO_API_BASE:-http://localhost:${DEMO_BACKEND_PORT}}"

PYTHON_BIN="${ROOT_DIR}/backend/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

api_base = os.environ.get("DEMO_API_BASE", "http://localhost:8010")
db_url = os.environ["JTA_DATABASE_URL"]
if not db_url.startswith("sqlite:///"):
    raise SystemExit("verify_demo.sh currently supports sqlite demo DB only")

db_path = Path(db_url.replace("sqlite:///", "", 1))
if not db_path.exists():
    raise SystemExit(f"demo database does not exist: {db_path}")

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("select count(*) from source_registry where source_key='demo_court_records'")
source_rows = cur.fetchone()[0]
if source_rows != 1:
    raise SystemExit("expected 1 demo source_registry row")

cur.execute("select is_active, requires_manual_review from source_registry where source_key='demo_court_records'")
is_active, requires_manual = cur.fetchone()
if is_active != 0 or requires_manual != 1:
    raise SystemExit("source_registry governance flags are not in expected fail-closed state")

cur.execute("select count(*) from source_snapshots where source_key='demo_court_records'")
snapshot_rows = cur.fetchone()[0]
if snapshot_rows < 2:
    raise SystemExit("expected at least 2 demo source snapshots")

cur.execute("select count(*) from review_items where source_url like 'https://demo.local/court/%'")
review_rows = cur.fetchone()[0]
if review_rows < 2:
    raise SystemExit("expected at least 2 demo review items")

cur.execute("select count(*) from audit_logs where action='demo_seed_data'")
audit_rows = cur.fetchone()[0]
if audit_rows < 1:
    raise SystemExit("expected demo_seed_data audit log row")

cur.execute("select review_status, public_visibility from events where event_id='DEMO-EVT-PUBLIC-001'")
public_row = cur.fetchone()
if public_row is None:
    raise SystemExit("public demo event missing")
if public_row[0] != "verified_court_record" or public_row[1] != 1:
    raise SystemExit("public demo event not in expected reviewed/public state")

cur.execute("select review_status, public_visibility from events where event_id='DEMO-EVT-PRIVATE-001'")
private_row = cur.fetchone()
if private_row is None:
    raise SystemExit("private demo event missing")
if private_row[0] != "pending_review" or private_row[1] != 0:
    raise SystemExit("private demo event not in expected pending/private state")

con.close()

try:
    with urllib.request.urlopen(f"{api_base}/health", timeout=3) as response:
        if response.status != 200:
            raise SystemExit("backend /health did not return 200")
except urllib.error.URLError as exc:
    raise SystemExit(f"backend not reachable at {api_base}: {exc}")

with urllib.request.urlopen(f"{api_base}/api/map/events", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))

features = payload.get("features", [])
feature_ids = {f.get("properties", {}).get("event_id") for f in features}
if "DEMO-EVT-PUBLIC-001" not in feature_ids:
    raise SystemExit("public demo event not returned by /api/map/events")
if "DEMO-EVT-PRIVATE-001" in feature_ids:
    raise SystemExit("private pending event leaked into /api/map/events")

print("Demo verification passed.")
print(f"API base: {api_base}")
print(f"Map feature count: {len(features)}")
print("Verified: reviewed/public visible, pending/private hidden, source registry and audit rows present.")
PY
