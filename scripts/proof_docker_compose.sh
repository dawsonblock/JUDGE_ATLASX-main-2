#!/usr/bin/env bash
set -euo pipefail

# Docker Compose smoke proof for Judge Atlas
# Usage: ./scripts/proof_docker_compose.sh
# Set KEEP_STACK=1 to preserve containers after test

KEEP_STACK="${KEEP_STACK:-0}"
JTA_DOCKER_COMPOSE_TIMEOUT="${JTA_DOCKER_COMPOSE_TIMEOUT:-600}"
COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../docker-compose.yml"
JTA_BACKEND_PORT="${JTA_BACKEND_PORT:-8000}"
JTA_FRONTEND_PORT="${JTA_FRONTEND_PORT:-3000}"
JTA_DB_PORT="${JTA_DB_PORT:-5432}"
JTA_REDIS_PORT="${JTA_REDIS_PORT:-6379}"
JTA_MINIO_PORT="${JTA_MINIO_PORT:-9000}"
JTA_MINIO_CONSOLE_PORT="${JTA_MINIO_CONSOLE_PORT:-9001}"
export JTA_BACKEND_PORT JTA_FRONTEND_PORT JTA_DB_PORT
export JTA_REDIS_PORT JTA_MINIO_PORT JTA_MINIO_CONSOLE_PORT

# Provide test-only placeholder tokens so CI/proof runs don't require a .env file
export JTA_ADMIN_TOKEN="${JTA_ADMIN_TOKEN:-proof-admin-token-ci}"
export JTA_ADMIN_REVIEW_TOKEN="${JTA_ADMIN_REVIEW_TOKEN:-proof-review-token-ci}"

log() { echo "[proof_docker] $*"; }

resolve_compose_command() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
        log "Using compose command: docker compose"
        return 0
    fi

    log "ERROR: docker compose plugin is not available"
    log "HINT: install Docker Desktop or the Docker Compose plugin"
    return 1
}

compose() {
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" "$@"
}

run_compose_with_timeout() {
    local timeout_seconds="$1"
    shift

    if command -v setsid >/dev/null 2>&1; then
        setsid "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" "$@" &
    else
        "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" "$@" &
    fi
    local cmd_pid="$!"

    (
        sleep "$timeout_seconds"
        kill -TERM "-$cmd_pid" 2>/dev/null || kill -TERM "$cmd_pid" 2>/dev/null || true
        sleep 1
        kill -KILL "-$cmd_pid" 2>/dev/null || kill -KILL "$cmd_pid" 2>/dev/null || true
    ) &
    local watchdog_pid="$!"

    local rc=0
    if ! wait "$cmd_pid"; then
        rc="$?"
    fi
    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    if [ "$rc" -eq 143 ] || [ "$rc" -eq 137 ]; then
        log "ERROR: compose command timed out after ${timeout_seconds}s: $*"
        return 142
    fi

    return "$rc"
}

compose_up_with_retry() {
    local attempts=6
    local delay_seconds=2
    local up_timeout_seconds="${JTA_DOCKER_COMPOSE_UP_TIMEOUT:-45}"
    local reconcile_timeout_seconds="${JTA_DOCKER_COMPOSE_RECONCILE_TIMEOUT:-30}"
    local out
    local rc
    local tmp

    for attempt in $(seq 1 "$attempts"); do
        log "Starting stack (attempt ${attempt}/${attempts})..."
        tmp="$(mktemp)"
        set +e
        run_compose_with_timeout "$up_timeout_seconds" up -d >"$tmp" 2>&1
        rc="$?"
        set -e
        out="$(cat "$tmp")"
        rm -f "$tmp"

        if [ "$rc" -eq 0 ]; then
            printf '%s\n' "$out"
            return 0
        fi

        if printf '%s' "$out" | grep -Eiq '(already in progress|already in use|has active endpoints|Conflict\. The container name)'; then
            log "WARN: docker reported a recoverable container/network conflict (attempt ${attempt}/${attempts}); retrying..."
            printf '%s\n' "$out"
            run_compose_with_timeout "$reconcile_timeout_seconds" down -v >/dev/null 2>&1 || true
            sleep "$delay_seconds"
            continue
        fi

        printf '%s\n' "$out"
        return "$rc"
    done

    log "ERROR: docker compose up failed after ${attempts} retries"
    return 1
}

dump_diagnostics() {
    log "Diagnostics: compose version"
    "${COMPOSE_CMD[@]}" version || true
    log "Diagnostics: compose config"
    compose config || true
    log "Diagnostics: compose ps"
    compose ps || true
    log "Diagnostics: backend logs"
    compose logs backend || true
    log "Diagnostics: frontend logs"
    compose logs frontend || true
    log "Diagnostics: db logs"
    compose logs db || true
}

cleanup() {
    if [ "$KEEP_STACK" != "1" ]; then
        log "Tearing down stack..."
        run_compose_with_timeout 180 down -v >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

resolve_compose_command

log "Step 1: Tearing down any existing stack..."
if ! run_compose_with_timeout "$JTA_DOCKER_COMPOSE_TIMEOUT" down -v; then
    log "WARN: initial compose down did not complete; continuing with rebuild"
fi

log "Step 2: Building images..."
"${COMPOSE_CMD[@]}" version
run_compose_with_timeout "$JTA_DOCKER_COMPOSE_TIMEOUT" build backend
run_compose_with_timeout "$JTA_DOCKER_COMPOSE_TIMEOUT" build frontend

log "Step 3: Starting stack..."
compose_up_with_retry || {
    log "ERROR: compose up failed"
    dump_diagnostics
    exit 1
}

log "Step 4: Waiting for backend health..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${JTA_BACKEND_PORT}/health" > /dev/null 2>&1; then
        log "Backend ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        log "ERROR: Backend not ready after 60s"
        dump_diagnostics
        exit 1
    fi
    sleep 1
done

log "Step 5: Checking /health endpoint..."
curl -sv "http://localhost:${JTA_BACKEND_PORT}/health" | head -100

log "Step 6: Checking /api/map/events endpoint..."
map_payload="$(curl -sf "http://localhost:${JTA_BACKEND_PORT}/api/map/events?bbox=-180,-90,180,90")" || {
    log "ERROR: map events endpoint check failed"
    dump_diagnostics
    exit 1
}
printf '%s\n' "$map_payload" | head -200

printf '%s' "$map_payload" | python3 -c 'import json,sys;json.load(sys.stdin)' >/dev/null || {
    log "ERROR: map events endpoint did not return valid JSON"
    dump_diagnostics
    exit 1
}

log "Step 7: Checking frontend root..."
curl -sf "http://localhost:${JTA_FRONTEND_PORT}/" > /dev/null && log "Frontend root: OK" || {
    log "ERROR: Frontend not reachable"
    dump_diagnostics
    exit 1
}

log "SUCCESS: Docker Compose smoke proof passed"
