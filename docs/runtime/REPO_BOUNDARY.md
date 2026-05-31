# Repository Boundary

> Status: Alpha — defines what is product code vs. research/reference material.

This document declares which directories are part of the **runtime product** and which are
**research, reference, or vendored material** that ships only for context.

---

## Runtime Product Tree (ships in release archive)

| Directory / File | Purpose |
|---|---|
| `backend/` | FastAPI application, Alembic migrations, ingestion adapters |
| `frontend/` | Next.js UI |
| `docs/` | Governance, architecture, and operational documentation |
| `scripts/` | CI, proof, and operational tooling scripts |
| `infra/` | Infrastructure provisioning (Bicep / Docker) |
| `artifacts/proof/current/` | Current alpha proof artifacts |
| `.github/` | CI/CD workflow definitions |
| `README.md`, `STATUS.md`, `CURRENT_STATUS.md` | Top-level release docs |
| `Makefile`, `docker-compose.yml`, `azure.yaml` | Build and orchestration entrypoints |

---

## Non-Shipping / Reference Trees

These directories are tracked in git for context and reproducibility, but are **excluded
from release archives** and must never contain runtime product code or credentials.

| Directory | Type | Notes |
|---|---|---|
| `research/` | Third-party research repos (vendored, read-only) | Renamed from `Research /` (trailing-space slug). Contains: `crawlee-python-master`, `Vane-master`, `cua-main`, `langextract-main` |
| `external/` | Vendored external dependencies | Should not be imported by product runtime code |
| `tools/` | Developer tooling registry | `registry.json` and `skills/` entries; not deployed |
| `skills/` | AI agent skill definitions for repo-local Copilot | Not part of application runtime |
| `demo/` | Demo data and scripts | For offline demos only; not deployed |
| `reports/` | Generated analysis reports | Informational; not deployed |

---

## Release Archive Exclusion Rules

The `scripts/build_release_archive.py` enforces these exclusions:

- `external/` — excluded via `EXCLUDED_PREFIXES`
- `research/` — excluded via `EXCLUDED_PREFIXES` (added Phase 1 hardening)
- `node_modules/`, `.venv/`, `__pycache__/` — excluded via `EXCLUDED_SEGMENTS`
- Credentials, `.env` files, private keys — excluded via `FORBIDDEN_FILE_NAMES`

See `scripts/validate_release_archive.py` for the validation contract.

---

## Boundary Violations

A **boundary violation** occurs when:
1. A non-shipping directory is imported by product runtime code.
2. A research/external directory is included in the release archive.
3. A stub or disabled source is exposed as a live feature.

Boundary violations are checked by `scripts/check_external_boundaries.py` and
`scripts/check_release_surface.py`.

---

*Last updated: Phase 1 hardening. See HARDENING_PLAN.md for full scope.*
