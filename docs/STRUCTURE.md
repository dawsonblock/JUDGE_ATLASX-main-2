# JUDGE_ATLASX Repository Structure

This document describes the organization of the JUDGE_ATLASX repository after Phase 1 cleanup (May 16, 2026).

## Principle

**Runtime code is strictly separated from reference, experimental, and archived materials.**

- **Production runtime** code lives in `/backend/`, `/frontend/`, `/deploy/`
- **All non-runtime materials** are isolated in `/external_reference/`
- **CI/CD gates** enforce this boundary
- **Startup guards** warn if boundary is violated

---

## Top-Level Directory Structure

### Production Runtime

| Directory | Purpose |
|-----------|---------|
| **`/backend`** | FastAPI Python application, Alembic migrations, SQLAlchemy models, ingestion adapters, evidence vault, auth system, API routes, tests |
| **`/frontend`** | Next.js 14 React application, map UI, admin dashboard, TypeScript, component library, tests |
| **`/deploy`** | Docker Compose stack, deployment configs, environment configs (dev/staging/production) |
| **`/scripts`** | Operational scripts: CI gates, proof generation, database backup/restore, cleanup utilities |
| **`/tests`** | End-to-end tests, integration tests (if separate from backend/frontend) |

### Documentation

| Directory | Purpose |
|-----------|---------|
| **`/docs`** | Organized documentation by category (see below) |
| **`docs/architecture/`** | System design, data flow, integration patterns, future roadmap |
| **`docs/security/`** | Auth model, RBAC, security policies, TLS enforcement, threat model |
| **`docs/evidence/`** | Evidence model, immutability rules, provenance tracking, lineage graph |
| **`docs/governance/`** | Publication policy, review workflow, jurisdiction rules, retention policy |
| **`docs/runtime/`** | Ingestion contracts, API documentation, source registry, AI safety rules |
| **`docs/status/`** | Current status, limitations, proof artifacts, release readiness |
| **`docs/data-model/`** | Database schema, ER diagrams, canonical entities |
| **`docs/deployment-guide/`** | Deployment procedures, prerequisites, Azure/Docker setup |

### Artifacts & Proof

| Directory | Purpose |
|-----------|---------|
| **`/artifacts`** | Proof artifacts, baseline reports, evidence lineage, contract definitions |
| **`artifacts/proof/current/`** | Current proof manifest, proof hash, scope report, excluded directories report |
| **`artifacts/contracts/`** | API contracts, data contracts, adapter contracts |
| **`artifacts/history/`** | Historical proof runs, archived baselines |

### Non-Runtime / Reference Materials (External Reference)

| Directory | Purpose |
|-----------|---------|
| **`/external_reference/`** | **ALL non-production code and reference materials** (see below) |

---

## External Reference Directory (`/external_reference/`)

This directory contains **all non-runtime materials** and is **completely isolated from production code**.

### Contents

| Subdirectory | Contents |
|--------------|----------|
| **`external_repos/`** | Third-party repositories for reference (CLI-Anything-main, memvid-Human--main-main, etc.) |
| **`legacy_disabled/`** | US-only ingestion adapters, deprecated code, marked with `NOT_RUNTIME` sentinels |
| **`archived_research/`** | Research projects (Vane-master, crawlee-python-master, langextract-main, etc.) |
| **`reference_only/`** | Immutable reference material, third-party specs, data source documentation |
| **`skills/`** | AI skill definitions, agent customization templates, non-runtime tooling |
| **`reports/`** | Generated reports, analysis outputs, historical documents |
| **`demo/`** | Demo scripts, sample data, screenshots, proof-of-concept materials |
| **`dist/`** | Build artifacts (if any; typically git-ignored) |
| **`.agents/`** | VS Code Copilot agent customization files |
| **`.codex/`** | Project metadata and configuration files |
| **`.claude/`** | Claude-specific project files |
| **`.notes/`** | Development notes and working documents |

### Isolation Rules

1. **No imports from `/external_reference/` in runtime code** (enforced by CI test `test_no_external_reference_imports.py`)
2. **Docker images exclude `/external_reference/`** by default
3. **Git history for production code is independent** of reference materials
4. **Startup guard warns if external_reference modules load** into the Python runtime

---

## Configuration Files

| File | Purpose |
|------|---------|
| **`docker-compose.yml`** | Local development stack (PostgreSQL, Redis, backend, frontend) |
| **`Dockerfile.backend`** | Backend image definition |
| **`.dockerignore`** | Exclude non-runtime files from Docker context |
| **`azure.yaml`** | Azure Developer CLI config (staging/production deployment) |
| **`Makefile`** | Common build/test/deploy targets |
| **`noxfile.py`** | Python automation tasks (pytest, linting, etc.) |

---

## Root-Level Documentation

| File | Purpose |
|------|---------|
| **`README.md`** | Project overview, quick-start, what JUDGE_ATLASX is/isn't |
| **`STRUCTURE.md`** | This file — repository organization |
| **`LICENSE`** | License (if applicable) |
| **`AI_BOUNDARY_RULES.md`** | AI safety rules and boundaries |
| **`STATUS.md`** | Current operational status |
| **`DEPLOYMENT.md`** | Deployment guide (or link to docs/deployment-guide/) |

---

## File Size & Boundaries

### What's in Runtime

- `/backend/app/` — ~5,000 lines of Python (models, services, routes, etc.)
- `/backend/alembic/` — Database migrations
- `/frontend/app/` — ~3,000 lines of TypeScript/React
- `/scripts/` — Operational utilities (not in Docker image)

### What's NOT in Runtime

- `/external_reference/` — Everything else (reference, experiments, tooling, etc.)
- `/docs/` — Documentation (may be included in deployment docs, not in runtime image)

---

## CI/CD Boundary Enforcement

### Test: `test_no_external_reference_imports.py`

- Runs before every CI build
- Parses all Python files in `/backend/app/`
- Fails if any `import external_reference` or `from external_reference` found
- Ensures `/external_reference/` remains isolated

### Command

```bash
pytest backend/app/tests/test_no_external_reference_imports.py -v
```

---

## Startup Guard

### Function: `_check_external_reference_not_loaded()`

- Runs on every FastAPI startup
- Checks `sys.modules` for loaded `external_reference` modules
- Logs warning if any found (non-fatal in dev, potential production flag)
- Located in `backend/app/main.py`

---

## Git Ignore

The `.gitignore` file ensures:

- `/external_reference/` **is tracked** (can be archived/tagged separately)
- `/backend/.venv/`, `/frontend/node_modules/` **are ignored**
- Build artifacts (`.pyc`, `dist/`, `build/`) **are ignored**
- Environment files (`.env.local`, `.env.production`) **are ignored** (use `.env.example`)

---

## Deployment

### Local Development (Docker Compose)

```bash
docker-compose up
```

Includes: PostgreSQL, Redis, FastAPI backend, Next.js frontend
Excludes: `/external_reference/` (not in Docker context)

### Production (Azure Container Apps)

Uses `/deploy/` configs and `azure.yaml`
Excludes: All reference materials, docs, demo

---

## Phase 1 Cleanup Summary

This structure was established during **Phase 1: Repository Cleanup + Boundary Enforcement**.

### Changes Made

1. ✅ Created `/external_reference/` and moved:
   - `/external/` → `/external_reference/external_repos/`
   - `/legacy_disabled/` → `/external_reference/legacy_disabled/`
   - `/research/` → `/external_reference/archived_research/`
   - `/reference_only/` → `/external_reference/reference_only/`
   - `/skills/` → `/external_reference/skills/`
   - `/reports/` → `/external_reference/reports/`
   - `/demo/` → `/external_reference/demo/`
   - Workspace configs (`.agents/`, `.codex/`, `.claude/`, `.notes/`) → `/external_reference/`

2. ✅ Organized `/docs/` into subdirectories:
   - `docs/architecture/`, `docs/security/`, `docs/evidence/`, etc.

3. ✅ Added CI boundary test: `test_no_external_reference_imports.py`

4. ✅ Added startup guard in `backend/app/main.py`: `_check_external_reference_not_loaded()`

### Verification

```bash
# Verify boundary test passes
pytest backend/app/tests/test_no_external_reference_imports.py -v

# Start application and check startup guard
docker-compose up backend

# Verify external_reference is properly isolated
ls -la external_reference/
```

---

## Next Steps (Phase 2+)

Once Phase 1 is complete and this structure is locked:

1. **Phase 2** — Canonical Data Model Lock (in `/backend/app/models/entities.py`)
2. **Phase 3** — Ingestion Hardening (in `/backend/app/ingestion/`)
3. **Phase 4–15** — Parallel work streams (evidence, sources, auth, review, search, AI, frontend, testing, observability, deployment)

Each phase adds features within the established `/backend/`, `/frontend/`, `/docs/`, `/scripts/` structure.

---

## Questions & Maintenance

- **"Where do I add new documentation?"** → Add `.md` files to appropriate `/docs/` subdirectory
- **"How do I add a new ingestion adapter?"** → Add Python file to `/backend/app/ingestion/source_adapters/`
- **"What about experimental AI features?"** → Keep in `/external_reference/skills/` until they graduate to runtime
- **"Can I reorganize `/docs/`?"** → Yes, as long as you update cross-references and this document

---

**Last Updated:** May 16, 2026 (Phase 1 Complete)
