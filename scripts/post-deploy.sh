#!/bin/bash
set -e

echo "=== JudgeTracker Atlas Post-Deploy Verification ==="

# Get outputs from azd
BACKEND_URL=$(azd env get-value BACKEND_URL 2>/dev/null || echo "")
FRONTEND_URL=$(azd env get-value FRONTEND_URL 2>/dev/null || echo "")

if [ -z "$BACKEND_URL" ]; then
    echo "WARNING: BACKEND_URL not found in azd environment"
    exit 0
fi

echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"

# Wait for services to be ready
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -sf "$BACKEND_URL/health" &>/dev/null; then
        echo "✓ Backend health check passed"
        break
    fi
    echo -n "."
    sleep 5
done

# Test API endpoints
echo ""
echo "Testing API endpoints..."

echo "- Testing /api/events..."
curl -sf "$BACKEND_URL/api/events?limit=1" &>/dev/null && echo "  ✓ Events endpoint OK" || echo "  ✗ Events endpoint failed"

echo "- Testing /api/map/events..."
curl -sf "$BACKEND_URL/api/map/events?limit=1" &>/dev/null && echo "  ✓ Map events endpoint OK" || echo "  ✗ Map events endpoint failed"

echo "- Testing /api/judges..."
curl -sf "$BACKEND_URL/api/judges?limit=1" &>/dev/null && echo "  ✓ Judges endpoint OK" || echo "  ✗ Judges endpoint failed"

# Check frontend
if [ -n "$FRONTEND_URL" ]; then
    echo ""
    echo "Testing frontend..."
    if curl -sf "$FRONTEND_URL" &>/dev/null; then
        echo "  ✓ Frontend responding"
    else
        echo "  ✗ Frontend not responding (may still be starting)"
    fi
fi

echo ""
echo "=== Verification complete ==="
echo ""
echo "Access your deployment:"
echo "  Frontend: $FRONTEND_URL"
echo "  Backend API: $BACKEND_URL"
echo "  API Docs: $BACKEND_URL/docs"
