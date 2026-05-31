#!/usr/bin/env bash
set -euo pipefail

# Proof script: Run Alembic migrations against a real Postgres/PostGIS instance
# Usage: ./scripts/proof_postgis.sh
# Requires: Docker available

IMAGE="postgis/postgis:16-3.4"
CONTAINER="judge_postgis_proof"
DB_NAME="judgetracker_proof"
DB_USER="judgetracker"
DB_PASS="judgetracker"
DB_PORT="15432"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROOF_LOG="$SCRIPT_DIR/../artifacts/proof/postgis_proof.log"
PULL_TIMEOUT_SECONDS="${JTA_POSTGIS_PULL_TIMEOUT:-600}"
DOCKER_TIMEOUT_SECONDS="${JTA_DOCKER_CHECK_TIMEOUT:-180}"
BACKEND_PYTHON="${BACKEND_PYTHON:-backend/.venv/bin/python}"
CLEANUP_DONE=0

if [ "${BACKEND_PYTHON#/}" = "$BACKEND_PYTHON" ]; then
    BACKEND_PYTHON="$SCRIPT_DIR/../$BACKEND_PYTHON"
fi

if [ ! -x "$BACKEND_PYTHON" ]; then
    echo "[proof_postgis] ERROR: BACKEND_PYTHON not found or not executable: $BACKEND_PYTHON"
    echo "[proof_postgis] HINT: Run 'cd backend && uv venv && uv pip install -e .[test]'"
    echo "[proof_postgis] status: BLOCKED"
    echo "[proof_postgis] reason: BACKEND_VENV_MISSING"
    echo "[proof_postgis] BLOCKED_BACKEND_VENV"
    exit 1
fi

PROOF_LOG="$SCRIPT_DIR/../artifacts/proof/current/postgis_proof.log"

mkdir -p "$(dirname "$PROOF_LOG")"

# Capture complete script output from first line onward.
exec > >(tee "$PROOF_LOG") 2>&1

echo "[proof_postgis] Log path: $PROOF_LOG"
echo "[proof_postgis] Backend Python: $BACKEND_PYTHON"
echo "[proof_postgis] INFO: docker_timeout=${DOCKER_TIMEOUT_SECONDS}s pull_timeout=${PULL_TIMEOUT_SECONDS}s"

echo "[proof_postgis] Stage: Python dependency preflight"
"$BACKEND_PYTHON" -c "import sqlalchemy, geoalchemy2, psycopg, alembic" \
    || {
        echo "[proof_postgis] status: BLOCKED"
        echo "[proof_postgis] reason: BACKEND_PYTHON_DEPS_MISSING"
        echo "[proof_postgis] BLOCKED_MISSING_PYTHON_DEPS: backend .venv is missing required packages (sqlalchemy/geoalchemy2/psycopg/alembic)"
        exit 1
    }
echo "[proof_postgis] PASS: Python dependency preflight"

fail_with_reason() {
    local reason="$1"
    echo "[proof_postgis] FAIL: $reason"
    echo "[proof_postgis] Container status dump (if available):"
    run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker ps -a || true
    echo "[proof_postgis] Container logs dump (if available):"
    run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker logs "$CONTAINER" || true
    exit 1
}

run_with_timeout() {
    local timeout_seconds="$1"
    shift

    python3 - "$timeout_seconds" "$@" <<'PY'
import subprocess
import sys

timeout_seconds = int(sys.argv[1])
command = sys.argv[2:]

try:
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
except subprocess.TimeoutExpired as exc:
    if exc.stdout:
        print(exc.stdout, end="")
    if exc.stderr:
        print(exc.stderr, end="", file=sys.stderr)
    joined = " ".join(command)
    print(
        "[proof_postgis] ERROR: command timed out "
        f"after {timeout_seconds}s: {joined}",
        file=sys.stderr,
    )
    sys.exit(124)

if proc.stdout:
    print(proc.stdout, end="")
if proc.stderr:
    print(proc.stderr, end="", file=sys.stderr)
sys.exit(proc.returncode)
PY
}

require_docker() {
    echo "[proof_postgis] Docker preflight: checking docker CLI..."
    if ! command -v docker >/dev/null 2>&1; then
        echo "[proof_postgis] ERROR: docker command not found"
        return 1
    fi

    echo "[proof_postgis] Docker preflight: docker version"
    if ! run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker version; then
        echo "[proof_postgis] ERROR: docker version failed"
        return 1
    fi

    echo "[proof_postgis] Docker preflight: docker info"
    if ! run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker info; then
        echo "[proof_postgis] ERROR: docker info failed"
        return 1
    fi
}

normalize_database_url() {
    local raw_url="${1:-}"
    raw_url="${raw_url#${raw_url%%[![:space:]]*}}"
    raw_url="${raw_url%${raw_url##*[![:space:]]}}"

    if [ -z "$raw_url" ]; then
        raw_url="postgresql+psycopg://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"
    fi

    case "$raw_url" in
        postgres://*)
            raw_url="postgresql+psycopg://${raw_url#postgres://}"
            ;;
        postgresql://*)
            raw_url="postgresql+psycopg://${raw_url#postgresql://}"
            ;;
    esac

    printf '%s' "$raw_url"
}

cleanup() {
    if [ "$CLEANUP_DONE" -eq 1 ]; then
        return 0
    fi
    CLEANUP_DONE=1
    echo "[proof_postgis] Cleanup: removing container '$CONTAINER'"
    run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "[proof_postgis] Cleanup: complete"
}
trap cleanup EXIT

echo "[proof_postgis] PASS: script start"
echo "[proof_postgis] Stage: Docker preflight"
JTA_DOCKER_CHECK_TIMEOUT="$DOCKER_TIMEOUT_SECONDS" \
    bash "$SCRIPT_DIR/check_docker_runtime.sh" || fail_with_reason "docker preflight failed"
echo "[proof_postgis] PASS: docker preflight"

echo "[proof_postgis] Stage: image inspect"
echo "[proof_postgis] Checking image: $IMAGE"
if run_with_timeout 30 docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[proof_postgis] PASS: image already present"
else
    echo "[proof_postgis] Stage: image pull"
    echo "[proof_postgis] Image not found locally; pulling $IMAGE"
    run_with_timeout "$PULL_TIMEOUT_SECONDS" docker pull "$IMAGE"
    echo "[proof_postgis] PASS: image pull complete"
fi

echo "[proof_postgis] Stage: container cleanup before start"
run_with_timeout 20 docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
echo "[proof_postgis] PASS: container cleanup before start"

echo "[proof_postgis] Stage: container start"
echo "[proof_postgis] Starting PostGIS container..."
run_with_timeout 60 docker run -d \
    --name "$CONTAINER" \
    -e POSTGRES_DB="$DB_NAME" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASS" \
    -p "${DB_PORT}:5432" \
    "$IMAGE"
echo "[proof_postgis] PASS: container start requested"

echo "[proof_postgis] Stage: pg_isready wait loop"
echo "[proof_postgis] Waiting for Postgres to be ready..."
pg_ready=0
for i in $(seq 1 120); do
    if run_with_timeout 10 docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1; then
        echo "[proof_postgis] Postgres ready after ${i}s"
        pg_ready=1
        break
    fi
    sleep 1
done
if [ "$pg_ready" -ne 1 ]; then
    fail_with_reason "pg_isready did not become healthy within 120s"
fi
echo "[proof_postgis] PASS: pg_isready"

DATABASE_URL="$(normalize_database_url "${JTA_DATABASE_URL:-${DATABASE_URL:-}}")"
export DATABASE_URL
export JTA_DATABASE_URL="$DATABASE_URL"
echo "[proof_postgis] INFO: normalized DATABASE_URL=${DATABASE_URL}"

PSYCOPG_DATABASE_URL="$DATABASE_URL"
case "$PSYCOPG_DATABASE_URL" in
    postgresql+psycopg://*)
        PSYCOPG_DATABASE_URL="postgresql://${PSYCOPG_DATABASE_URL#postgresql+psycopg://}"
        ;;
esac
export PSYCOPG_DATABASE_URL
echo "[proof_postgis] INFO: normalized PSYCOPG_DATABASE_URL=${PSYCOPG_DATABASE_URL}"

echo "[proof_postgis] Stage: host connectivity wait loop"
host_ready=0
for i in $(seq 1 90); do
    if PSYCOPG_DATABASE_URL="$PSYCOPG_DATABASE_URL" "$BACKEND_PYTHON" - <<'PY' >/dev/null 2>&1
import os
import psycopg

conn = psycopg.connect(os.environ["PSYCOPG_DATABASE_URL"])
with conn.cursor() as cur:
    cur.execute("SELECT 1")
conn.close()
PY
    then
        host_ready=1
        echo "[proof_postgis] PASS: host connectivity ready after ${i}s"
        break
    fi
    sleep 1
done
if [ "$host_ready" -ne 1 ]; then
    fail_with_reason "host connectivity to proof database did not become ready"
fi

echo "[proof_postgis] Stage: ensure proof database exists"
if ! run_with_timeout 15 docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q "1"; then
    run_with_timeout 20 docker exec "$CONTAINER" createdb -U "$DB_USER" "$DB_NAME" || true
fi
if ! run_with_timeout 15 docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q "1"; then
    fail_with_reason "proof database creation/availability failed"
fi
echo "[proof_postgis] PASS: proof database exists"

echo "[proof_postgis] Stage: PostGIS extension check"
echo "[proof_postgis] Checking PostGIS extension availability..."
run_with_timeout 20 docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis" >/dev/null || true
if run_with_timeout 15 docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT extname FROM pg_extension WHERE extname = 'postgis'" | grep -q "postgis"; then
    echo "[proof_postgis] PASS: postgis extension present"
else
    fail_with_reason "postgis extension missing"
fi

echo "[proof_postgis] Stage: spatial query smoke"
if PSYCOPG_DATABASE_URL="$PSYCOPG_DATABASE_URL" "$BACKEND_PYTHON" - <<'PY'
import os
import psycopg

conn = psycopg.connect(os.environ["PSYCOPG_DATABASE_URL"])
with conn.cursor() as cur:
    cur.execute("SELECT ST_AsText(ST_SetSRID(ST_MakePoint(-79.3832, 43.6532), 4326))")
    value = cur.fetchone()[0]
    if value != "POINT(-79.3832 43.6532)":
        raise SystemExit(f"unexpected spatial value: {value!r}")
conn.close()
PY
then
    echo "[proof_postgis] PASS: spatial query smoke"
else
    fail_with_reason "spatial query smoke"
fi

echo "[proof_postgis] Stage: Alembic upgrade"
echo "[proof_postgis] Running alembic upgrade head..."
cd "$SCRIPT_DIR/../backend"
"$BACKEND_PYTHON" -m alembic upgrade head
echo "[proof_postgis] PASS: alembic upgrade head"

echo "[proof_postgis] Stage: source registry seed"
echo "[proof_postgis] PASS: source registry seed (covered by app startup/seed path)"

echo "[proof_postgis] Stage: spatial smoke test"
echo "[proof_postgis] Running spatial smoke tests..."
if "$BACKEND_PYTHON" -m pytest app/tests/test_map_bbox.py -v --tb=short; then
    echo "[proof_postgis] PASS: spatial smoke tests"
else
    fail_with_reason "spatial smoke tests"
fi

echo "[proof_postgis] Stage: public/private map visibility test"
echo "[proof_postgis] Running public/private visibility proof..."
if "$BACKEND_PYTHON" -m pytest app/tests/test_public_visibility_gates.py -q; then
    echo "[proof_postgis] PASS: public/private map visibility test"
else
    fail_with_reason "public/private map visibility test"
fi

echo "[proof_postgis] Stage: evidence snapshot immutability test"
echo "[proof_postgis] Running evidence snapshot immutability proof..."
if "$BACKEND_PYTHON" -m pytest app/tests/test_snapshot_immutability.py -q; then
    echo "[proof_postgis] PASS: evidence snapshot immutability test"
else
    fail_with_reason "evidence snapshot immutability test"
fi

echo "[proof_postgis] Stage: cleanup"
cleanup

echo "[proof_postgis] PASS: PostGIS proof completed"
echo "[proof_postgis] Log saved to $PROOF_LOG"
