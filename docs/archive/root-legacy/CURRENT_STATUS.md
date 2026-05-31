# Current Status

- Canonical status: `STATUS.md`
- Canonical current proof: `artifacts/proof/current/CURRENT_PROOF.md`
- Canonical release readiness: `artifacts/proof/current/release_readiness.md`
- Alpha proof status: PASS
- Production ready: FALSE

Date: 2026-05-13

Release status: **alpha / reviewer-assisted / evidence-linked / source-dependent**.

## External/ directory

`external/` contains reference systems only — `CLI-Anything-main` and `memvid-Human--main-main`. Neither is imported by, vendored into, or required for the JUDGE-main runtime. They must not be treated as runtime dependencies, authoritative data stores, or production infrastructure.

## Operational today

- FastAPI backend with SQLAlchemy, Alembic, source registry, evidence snapshots, review queues, and audit log models.
- Next.js frontend with a MapLibre map workspace and admin/source/review surfaces.
- Local Docker Compose stack for Postgres/PostGIS, Redis, backend, and frontend.
- Click-based `judgectl` CLI with existing source, ingest, archive, audit, and health command patterns.
- Canada/Saskatchewan source registry YAML with explicit non-runnable classifications for unsupported sources.
- Justice Canada XML ingestion is runtime-enabled under canonical source key `justice_canada_laws_xml` with review-required/public-private defaults.
- Frontend production build completes cleanly with Next.js tracing scoped under `experimental.outputFileTracingRoot`.

## Source register states

Each source is classified by `source_class` and must be treated accordingly:

| Class | Meaning | Auto-ingestion allowed |
| --- | --- | --- |
| `machine_ingest` | Automated HTTP fetch + parser pipeline, parser version declared | Yes — after contract validation |
| `portal_reference` | Data exists on a public portal; no automated fetch pipeline | No — manual/portal only |
| `manual_upload` | Data arrives as human-supplied file uploads | No — human-gated |
| `disabled_stub` | Source is registered but intentionally non-operational | No |
| `None` (legacy) | Treated as `machine_ingest`; must be migrated or quarantined | Quarantine-gated |

Sources in `portal_reference`, `manual_upload`, or `disabled_stub` must never be promoted to auto-ingest without an explicit registry update and contract validation proof.

## Memory layer

`backend/app/memory/` is a **derivative layer** — it rebuilds summaries from authoritative evidence snapshots. Memory is not authoritative storage, not a primary source of truth, and does not replace or supersede evidence records. Public-facing answers that rely on memory claims must carry an explicit `ai_generated: true` and `requires_human_review: true` flag.

## AI layer

`backend/app/ai/` modules are **citation-bounded reviewer-assistance tools only**. No AI module produces guilt, danger, or corruption scores as publishable fields. All AI output is of type `reviewer_suggestion` and requires human review before any public action. AI modules are not legal adjudicators, do not deliver accountability conclusions autonomously, and do not produce binding legal findings.

## Not yet acceptable for public production use

- Shared-token admin compatibility remains for development and must not be used as public deployment auth.
- JWT/RBAC/session management needs final role alignment and mutation-route proof.
- Evidence lineage exists but needs full immutable snapshot, replay, and duplicate-detection proof.
- Canadian law and legislation ingestion is partial and coverage remains incomplete.
- Source adapters are source-dependent. Portal-only or unsupported sources are not automated ingestion pipelines.
- AI modules are reviewer-assistance/rule-based helpers, not legal adjudication.

## Required proof before a release candidate

1. Backend editable install and pytest pass.
2. Alembic single-head and upgrade proof pass.
3. Frontend `npm ci`, typecheck, and build pass.
4. Docker stack boots with explicit local secrets and smoke tests pass.
5. Source registry validation passes.
6. Banned-claim check passes.
7. Mutation endpoints enforce JWT/RBAC and write audit records with actor and before/after state.

## Mechanical enforcement (active)

The following architectural invariants are mechanically enforced by CI and start-up guards.
They are no longer aspirational — violation blocks merge or process start.

| # | Invariant | Enforced by |
|---|-----------|-------------|
| 1 | Ingestion modules that are not runtime-safe carry `NOT_RUNTIME = True`; the check script rejects any that do not | `scripts/check_no_direct_ingestion_network_clients.py` Check 3; CI guard step |
| 2 | No production ingestion module imports `httpx`/`requests`/`aiohttp` directly at module level without `NOT_RUNTIME` | same script Check 1/2; CI guard step |
| 3 | `automation_status` is a gate: `enable_source` requires `machine_ready_disabled`; `run_source_now` requires `machine_ready_disabled` or `machine_ready_enabled` | `admin_sources.py`, `source_registry_ctl.py`; `automation_statuses.py` |
| 4 | `parser_version` mismatch between source registry and ingest result is a contract violation | `source_runner._validate_machine_ingest_contract()` |
| 5 | `COMPLETED_WITH_ERRORS` is deprecated compatibility only; `COMPLETED_WITH_WARNINGS` is canonical and is the only partial-success status new code should write | `statuses.py` |
| 6 | `RunPersistSummary` carries `quarantined_count`, `failed_records`, `review_items_skipped`, `warnings` — no shared mutable defaults | `source_runner.py` (dataclass `field(default_factory=list)`) |
| 7 | Full enforcement proof run with timestamped artifacts via `nox -s enforcement` | `scripts/run_enforcement_proof.sh`; `noxfile.py` |
| 8 | `PYTHONDONTWRITEBYTECODE=1` on all CI compile steps (no `.pyc` from CI) | `.github/workflows/quality-gate.yml` |
| 9 | Production start refuses with `sys.exit(1)` if `JTA_FETCH_EGRESS_PROXY` is unset and `JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY` is also unset | `main._validate_production_safety()` |
| 10 | Repo boundary check (`check_repo_boundaries.py`) runs in CI | `.github/workflows/quality-gate.yml` |
