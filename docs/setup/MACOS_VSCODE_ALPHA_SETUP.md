# macOS + VS Code Alpha Setup

This setup path is for local alpha operation only.

## Alpha Warning

This system is an alpha. Public-facing records require human review and evidence snapshots. Production readiness is false.

## 1) Baseline prerequisites

- Python 3.11.x
- Node 20.x
- npm 10.x
- Optional local services: PostgreSQL/PostGIS, Redis, Docker Desktop or Colima

## 2) Configuration files

Copy and review environment examples:

- cp .env.example .env
- cp backend/.env.example backend/.env (optional backend-local override)
- cp frontend/.env.example frontend/.env.local (optional frontend-local override)

## 3) Required environment contract

Backend/runtime keys:

- JTA_APP_ENV=development
- JTA_RUNTIME_PROFILE=alpha_local
- JTA_DATABASE_URL=postgresql+psycopg://... or sqlite:///...
- JTA_REDIS_URL=redis://localhost:6379/0
- JTA_JWT_SECRET_KEY=replace_with_long_random_secret
- JTA_JWT_ALGORITHM=HS256
- JTA_CORS_ORIGINS=http://localhost:3000
- JTA_EVIDENCE_STORE_ROOT=./artifacts/evidence-store
- JTA_EVIDENCE_STORE_REQUIRED=false
- JTA_STORAGE_BACKEND=local
- JTA_ENABLE_PUBLIC_PLATFORM=false
- JTA_ENABLE_EXPERIMENTAL_LIVE_MAP=false
- JTA_ENABLE_WORKFLOW_ADMIN=false
- JTA_ENABLE_LEGACY_ADMIN_TOKEN=false
- JTA_FETCH_EGRESS_PROXY=
- JTA_RATE_LIMIT_BACKEND=memory
- JTA_INGESTION_QUEUE_BACKEND=inprocess

Frontend keys:

- NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
- NEXT_PUBLIC_ENABLE_LIVE_MAP=false
- NEXT_PUBLIC_ENABLE_ADMIN_UI=true

## 4) Bootstrap

Run the guided bootstrap:

- bash scripts/bootstrap_macos_alpha.sh

## 5) Environment verification

Run the local environment report:

- python3 scripts/check_local_dev_environment.py

Expected output includes PASS/WARN/FAIL lines and a machine-readable JSON summary.

## 6) Config/documentation consistency

Run:

- python3 scripts/check_config_docs_consistency.py

This ensures config keys in code, env examples, and setup/deployment docs stay aligned.

## 7) Start application

- make dev

or

- make setup
- make backend-test
- make frontend-check
