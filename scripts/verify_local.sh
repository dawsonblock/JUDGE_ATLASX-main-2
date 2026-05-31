#!/usr/bin/env bash
set -euo pipefail

echo "Python:"
python --version

cd backend

echo "Backend install:"
python -m pip install -e ".[test]"

echo "Backend compile:"
python -m compileall -q app

echo "Backend tests:"
python -m pytest -q

cd ../frontend

echo "Node:"
node --version

echo "npm:"
npm --version

echo "Frontend install:"
npm ci

echo "Frontend lint:"
npm run lint

echo "Frontend typecheck:"
npm run typecheck

echo "Frontend build:"
npm run build
