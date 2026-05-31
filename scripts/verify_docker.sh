#!/bin/bash
set -e

cd "$(dirname "$0")/.."

fail() {
    echo "FAIL: $1" >&2
    docker compose logs backend >&2 || true
    docker compose down >&2 || true
    exit 1
}

echo "=== Docker Verification ==="
echo "1. Building images..."
docker compose build

echo "2. Starting services..."
docker compose up -d

echo "3. Waiting for backend to become healthy..."
for i in $(seq 1 30); do
    STATUS=$(docker compose ps --format json backend 2>/dev/null \
             | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health',''))" 2>/dev/null || echo "")
    if [ "$STATUS" = "healthy" ]; then break; fi
    echo "  attempt $i/30 — status: ${STATUS:-starting}"
    sleep 3
done
docker compose ps backend | grep -q "healthy" || fail "Backend never became healthy"

echo "4. Health endpoint check..."
curl -fsS http://localhost:8000/health > /dev/null \
    || fail "GET /health returned non-2xx"

echo "5. Map events check..."
curl -fsS "http://localhost:8000/api/map/events" > /dev/null \
    || fail "GET /api/map/events returned non-2xx"

echo "6. Crime incidents check..."
curl -fsS "http://localhost:8000/api/map/crime-incidents" > /dev/null \
    || fail "GET /api/map/crime-incidents returned non-2xx"

echo "7. Admin import endpoint rejects unauthenticated request..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:8000/api/admin/ingest/courtlistener-bulk/list)
[ "$HTTP_CODE" = "403" ] \
    || fail "Admin import endpoint should return 403 without token, got $HTTP_CODE"

echo "8. Alembic heads check inside container..."
docker compose exec -T backend alembic heads 2>&1 | grep -v "^$" \
    || fail "alembic heads failed inside container"
docker compose exec -T backend alembic heads 2>&1 | grep -c "head" | grep -q "^1$" \
    || fail "Expected exactly 1 Alembic head"

echo "9. Cleanup..."
docker compose down

echo ""
echo "=== Docker verification PASSED ==="
