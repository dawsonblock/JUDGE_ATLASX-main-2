# Repository Reality Audit

Date: 2026-05-06

This audit is intentionally conservative. A component is listed as working only when it has a clear runtime path, tests or verification scripts, and no known dependency on unavailable services. JUDGE-main is the only runtime authority. CLI-Anything-main and memvid-Human--main-main are reference systems and are not imported by the application runtime.

## Status vocabulary

- `WORKING`: implemented, wired into a runtime path, and covered by tests or verification scripts.
- `PARTIAL`: implemented in part, but missing production hardening, complete source coverage, or end-to-end proof.
- `STUB`: intentionally present but not runnable as a real pipeline or source.
- `DEAD`: not part of any supported runtime path and retained only until removal or migration.
- `EXPERIMENTAL`: usable for research or local validation, but not authoritative infrastructure.

## Runtime boundary

| Area                         | Status         | Reality                                                                                                |
| ---------------------------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| `JUDGE-main`                 | `WORKING`      | Authoritative FastAPI, Next.js, Postgres/PostGIS, Redis, evidence, ingestion, and CLI code lives here. |
| `CLI-Anything-main`          | `EXPERIMENTAL` | Reference command architecture only. Do not vendor or import it into JUDGE runtime.                    |
| `memvid-Human--main-main`    | `EXPERIMENTAL` | Optional archive/search sidecar candidate. It is not authoritative storage.                            |
| Workspace root solution file | `DEAD`         | Legacy/editor artifact; not the Python/Next.js runtime.                                                |

## Backend module classification

| Module                                  | Status         | Evidence and limitations                                                                                                                                                       |
| --------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `backend/app/main.py`                   | `WORKING`      | FastAPI app factory, route registration, safety checks, scheduler gate. Must continue to boot under tests and Docker.                                                          |
| `backend/app/api/routes`                | `PARTIAL`      | Public/admin route surface exists. Mutation routes need complete JWT/RBAC and before/after audit verification.                                                                 |
| `backend/app/auth`                      | `PARTIAL`      | JWT and shared-token compatibility exist. Role vocabulary still needs alignment to `viewer`, `reviewer`, `source_admin`, `admin`, `owner`; shared tokens must remain dev-only. |
| `backend/app/core`                      | `WORKING`      | Settings, request utilities, and rate-limit infrastructure exist. Production safety checks must remain fail-closed.                                                            |
| `backend/app/db`                        | `PARTIAL`      | SQLAlchemy and PostGIS helpers exist. Needs migration proof, index review, partitioning/RLS decision, and GIS performance proof.                                               |
| `backend/app/models`                    | `PARTIAL`      | Domain, source, user, audit, evidence, and memory models exist. Needs complete evidence-lineage constraints and role/session model hardening.                                  |
| `backend/app/schemas`                   | `PARTIAL`      | API schemas exist but need full auth/evidence/source validation alignment.                                                                                                     |
| `backend/app/serializers`               | `WORKING`      | Runtime serializers exist for map/API records; must keep verified/unverified state explicit.                                                                                   |
| `backend/app/services`                  | `PARTIAL`      | Evidence store, source control, graph, publication rules, and review services exist. AI-adjacent services must remain reviewer-assistance only.                                |
| `backend/app/services/pipeline`         | `EXPERIMENTAL` | Pipeline runtime scaffolding exists; use only where tests prove behavior.                                                                                                      |
| `backend/app/evidence`                  | `PARTIAL`      | Hashing, extraction, provenance, snapshots, integrity runtime exist. Needs immutable snapshot enforcement and replay/duplicate proof.                                          |
| `backend/app/evidence/runtime`          | `PARTIAL`      | Content addressing, lifecycle, retention, integrity utilities exist. Needs operational proof against real evidence snapshots.                                                  |
| `backend/app/ingestion`                 | `PARTIAL`      | Source registry, adapters, runner, dedupe, replay, and normalization exist. Only validated `machine_ingest` sources may run.                                                   |
| `backend/app/ingestion/source_adapters` | `PARTIAL`      | Several Canada-first adapters exist. Each adapter must prove legal/source endpoint, snapshot, checksum, retry, parser version, and fixture tests before runnable status.       |
| `backend/app/ingestion/crime_sources`   | `PARTIAL`      | Saskatoon/StatsCan/manual import code exists. Portal-only or unsupported sources must stay non-runnable.                                                                       |
| `backend/app/ingestion/laws`            | `STUB`         | Canadian law ingestion contains placeholder/limited extraction paths; legal coverage is incomplete.                                                                            |
| `backend/app/ingestion/web_monitor`     | `EXPERIMENTAL` | Web monitor is review-only and must not create authoritative incident records automatically.                                                                                   |
| `backend/app/archive`                   | `PARTIAL`      | JSONL/archive export support exists. memvid integration is optional and non-authoritative.                                                                                     |
| `backend/app/memory`                    | `EXPERIMENTAL` | Derivative memory/rebuild layer exists. No claim should describe it as authoritative storage or complete semantic recall.                                                      |
| `backend/app/memory/runtime`            | `EXPERIMENTAL` | Runtime lifecycle helpers exist; keep public visibility gates and evidence dependency explicit.                                                                                |
| `backend/app/graph`                     | `PARTIAL`      | Graph query support exists. Relationships require evidence and visibility gates.                                                                                               |
| `backend/app/ai`                        | `EXPERIMENTAL` | Deterministic/rule-based reviewer-assistance modules. Not AGI, not legal adjudication, not automatic publishing.                                                               |
| `backend/app/cli`                       | `PARTIAL`      | Click-based `judgectl` exists. Must standardize `--json`, `--dry-run`, `--verbose` across required commands.                                                                   |
| `backend/app/workers`                   | `PARTIAL`      | Scheduler/job scaffolding exists and is disabled by default. Needs source-class and registry gates on every path.                                                              |
| `backend/app/seed`                      | `WORKING`      | Source registry and sample seed paths exist. Production must not depend on sample data.                                                                                        |
| `backend/app/tests`                     | `WORKING`      | Large pytest suite exists. Full current pass must be proven after every milestone.                                                                                             |

## Frontend module classification

| Module                                                                 | Status         | Evidence and limitations                                                                                                    |
| ---------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `frontend/app/dashboard`                                               | `WORKING`      | SSR dashboard exists; must continue handling backend fallbacks safely.                                                      |
| `frontend/app/judges`, `frontend/app/cases`, `frontend/app/defendants` | `WORKING`      | Entity pages exist for current API shape.                                                                                   |
| `frontend/app/sources`                                                 | `WORKING`      | Public source listing exists.                                                                                               |
| `frontend/app/admin`                                                   | `PARTIAL`      | Admin/review/source UI exists. Needs JWT/session-aware flows and stricter RBAC UX.                                          |
| `frontend/app/admin/ai-checks`                                         | `EXPERIMENTAL` | AI checks page is reviewer-assistance only and must not imply autonomous judgment.                                          |
| `frontend/app/map`                                                     | `DEAD`         | Legacy Leaflet route. Keep only as labeled legacy/redirect until removed.                                                   |
| `frontend/app/map`                                                     | `PARTIAL`      | Canonical MapLibre workspace exists. Needs verified/unverified separation, evidence drawer, timeline, filters, audit trail. |
| `frontend/app/api`                                                     | `PARTIAL`      | Server-side route handlers/proxies exist. Ensure no admin token reaches browser code.                                       |
| `frontend/components/maplibre`                                         | `PARTIAL`      | MapLibre components exist. Needs layer separation and review/evidence UX completion.                                        |
| `frontend/components/map`                                              | `PARTIAL`      | Transitional map components; audit for legacy Leaflet coupling before removal.                                              |
| `frontend/components/crime-map`                                        | `PARTIAL`      | Live crime map/evidence chat pieces exist. Must preserve review and public-visibility gates.                                |
| `frontend/components/ui`                                               | `WORKING`      | shadcn/Radix-style primitives exist and should be preserved.                                                                |
| `frontend/lib/api.ts`                                                  | `PARTIAL`      | Typed API client exists. Needs JWT/session migration and stronger contract tests.                                           |

## Infrastructure and operations classification

| Module                          | Status         | Reality                                                                                                  |
| ------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------- |
| `docker-compose.yml`            | `PARTIAL`      | Local PostGIS/Redis/backend/frontend stack exists. Full proof must validate with explicit tokens.        |
| `infra`                         | `EXPERIMENTAL` | Azure Container Apps/Bicep path exists but is not the current repair authority until validated.          |
| `scripts/proof_all.sh`          | `PARTIAL`      | Existing proof script exists; superseded by `scripts/proof_full_stack.sh` for clean full-stack evidence. |
| `scripts/validate_workflows.py` | `WORKING`      | YAML source validator exists and remains part of the quality gate.                                       |
| `artifacts/proof`               | `EXPERIMENTAL` | Historical proof logs only; current proof must be regenerated after changes.                             |

## Source adapter register classification

Each entry in `ADAPTER_REGISTRY` is linked to one or more source registry rows.
`source_class` is controlled by the YAML registry, not by the adapter code.
An adapter classified as `portal_reference` or `disabled_stub` **must not** be used
in an automated machine-ingest run.

| Adapter class                 | `parser` key             | source_class (registry)                                       | Contract-validated       | Notes                                                                                     |
| ----------------------------- | ------------------------ | ------------------------------------------------------------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| `SaskatoonCsvAdapter`         | `saskatoon_csv`          | `portal_reference`                                            | No                       | City of Saskatoon has not published crime-incident CSV; automated fetch blocked           |
| `SaskatoonPoliceCsvAdapter`   | `saskatoon_police_csv`   | `portal_reference`                                            | No                       | SPS ToS 2026 explicitly prohibits machine comparison over time                            |
| `CrawleePoliceReleaseAdapter` | `crawlee_police_release` | `disabled_stub`                                               | No                       | Adapter not yet implemented; two registry stubs (SPS + RCMP)                              |
| `SKCourtsHtmlAdapter`         | `sk_courts_html`         | No registered source                                          | No                       | Adapter exists but has no corresponding registry entry; treat as `disabled_stub`          |
| `StatscanTableAdapter`        | `statscan_table`         | `portal_reference`                                            | No                       | Stats Canada CKAN portal; no direct resource_id configured                                |
| `CanLIIApiAdapter`            | `canlii_api`             | `machine_ingest` (KB/CA), `portal_reference` (generic CanLII) | machine_ingest rows only | Requires `CANLII_API_KEY`; dedicated QB/CA sources validated 2026-05-06                   |
| `FederalCourtHtmlAdapter`     | `federal_court_html`     | `machine_ingest`                                              | Yes                      | Endpoint validated 2026-05-06 (decisions.fct-cf.gc.ca iframe)                             |
| `SCCLexumApiAdapter`          | `scc_lexum_api`          | `machine_ingest`                                              | Yes                      | RSS validated 2026-05-06 (decisions.scc-csc.ca)                                           |
| `CrawleeGovNewsAdapter`       | `crawlee_gov_news`       | `disabled_stub`                                               | No                       | Adapter not yet implemented; SK Justice Ministry stub                                     |
| `SKLegislatureHtmlAdapter`    | `sk_legislature_html`    | `machine_ingest`                                              | Yes                      | Hansard index validated 2026-05-06                                                        |
| `LawsJusticeHtmlAdapter`      | `laws_justice_html`      | `machine_ingest`                                              | Yes                      | Criminal Code amendments page validated 2026-05-06                                        |
| `CKANApiAdapter`              | `ckan_api`               | `portal_reference`                                            | No                       | Both consumer sources lack `resource_id`; re-promote only after factory config_json wired |

## Immediate repair priorities

1. Enforce truth-claim checks and maintain these audit files as release gates.
2. Stabilize install/build/test commands with bootstrap scripts and nox sessions.
3. Complete JWT/RBAC and mutation audit hardening before any public deployment.
4. Keep non-runnable or legally unsupported source adapters classified as `portal_reference` or `disabled_stub`.
5. Promote MapLibre to the canonical map while preserving verified/unverified separation.
6. Register a source entry for `sk_courts_html` adapter or remove the adapter if no longer needed.
