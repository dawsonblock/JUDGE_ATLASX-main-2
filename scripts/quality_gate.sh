#!/usr/bin/env bash
# Architecture Quality Gate for JudgeTracker Atlas
# Runs: sentrux, backend compile/tests, frontend lint/typecheck/build

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Allow sentrux to be missing if explicitly allowed
ALLOW_MISSING_SENTRUX="${ALLOW_MISSING_SENTRUX:-0}"

echo "========================================"
echo "JudgeTracker Atlas Quality Gate"
echo "========================================"
echo ""

# Track failures
FAILURES=0

# 1. Run Sentrux checks (if available)
echo "🔍 Step 1: Sentrux Architecture Checks"
echo "----------------------------------------"

if command -v sentrux &> /dev/null; then
    if sentrux check "$PROJECT_ROOT"; then
        echo -e "${GREEN}✓ Sentrux checks passed${NC}"
    else
        echo -e "${RED}✗ Sentrux checks failed${NC}"
        FAILURES=$((FAILURES + 1))
    fi
else
    if [ "$ALLOW_MISSING_SENTRUX" = "1" ]; then
        echo -e "${YELLOW}⚠ sentrux not found, skipping (ALLOW_MISSING_SENTRUX=1)${NC}"
    else
        echo -e "${RED}✗ sentrux not found${NC}"
        echo "   Install with: pip install sentrux"
        echo "   Or run with: ALLOW_MISSING_SENTRUX=1 $0"
        FAILURES=$((FAILURES + 1))
    fi
fi

echo ""

# 2. Backend checks
echo "🔧 Step 2: Backend Checks"
echo "----------------------------------------"

cd "$PROJECT_ROOT/backend"

# Check virtual environment
if [ ! -d ".venv" ] && [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ No virtual environment found${NC}"
    echo "   Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing backend dependencies..."
    pip install -q -e ".[test]"
fi

# Compile check
echo "Running compile check..."
if python -m compileall app/ -q 2>/dev/null; then
    echo -e "${GREEN}✓ Backend compile check passed${NC}"
else
    echo -e "${RED}✗ Backend compile check failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

# Run tests
echo "Running test suite..."
if python -m pytest -q --tb=short 2>&1 | tail -5; then
    echo -e "${GREEN}✓ Backend tests passed${NC}"
else
    echo -e "${RED}✗ Backend tests failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""

# 3. Frontend checks
echo "🎨 Step 3: Frontend Checks"
echo "----------------------------------------"

cd "$PROJECT_ROOT/frontend"

# Check node_modules
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install --silent
fi

# Lint
echo "Running lint..."
if npm run lint --silent 2>/dev/null; then
    echo -e "${GREEN}✓ Frontend lint passed${NC}"
else
    echo -e "${RED}✗ Frontend lint failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

# Type check
echo "Running type check..."
if npx tsc --noEmit 2>/dev/null; then
    echo -e "${GREEN}✓ Frontend type check passed${NC}"
else
    echo -e "${RED}✗ Frontend type check failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

# Build
echo "Running build..."
if npm run build --silent 2>&1 | tail -3; then
    echo -e "${GREEN}✓ Frontend build passed${NC}"
else
    echo -e "${RED}✗ Frontend build failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""

# 4. Security & governance checks
echo "🔒 Step 4: Security & Governance Checks"
echo "----------------------------------------"

# 4a. Admin token must not leak into frontend components or lib
echo "Checking admin token confinement..."
LEAKED=$(grep -rl "JTA_ADMIN_TOKEN" \
    "$PROJECT_ROOT/frontend/components/" \
    "$PROJECT_ROOT/frontend/lib/" \
    2>/dev/null | wc -l | tr -d ' ')
if [ "$LEAKED" -eq 0 ]; then
    echo -e "${GREEN}✓ JTA_ADMIN_TOKEN not found in frontend/components/ or frontend/lib/${NC}"
else
    echo -e "${RED}✗ JTA_ADMIN_TOKEN leaked into frontend non-route files (${LEAKED} file(s))${NC}"
    grep -rl "JTA_ADMIN_TOKEN" \
        "$PROJECT_ROOT/frontend/components/" \
        "$PROJECT_ROOT/frontend/lib/" \
        2>/dev/null
    FAILURES=$((FAILURES + 1))
fi

# 4b. YAML source workflow validator
echo "Running YAML source validator..."
if python3 "$PROJECT_ROOT/scripts/validate_workflows.py" 2>&1; then
    echo -e "${GREEN}✓ YAML source validator passed${NC}"
else
    echo -e "${RED}✗ YAML source validator failed${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""

# Summary
echo "========================================"
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✓ All quality gate checks passed!${NC}"
    echo "========================================"
    exit 0
else
    echo -e "${RED}✗ $FAILURES quality gate check(s) failed${NC}"
    echo "========================================"
    exit 1
fi
