# Stubs and Placeholders

Date: 2026-05-09 (updated for JUDGE_ATLAS-main 14 repairs)

Stubs are kept visible so they cannot be mistaken for operational features.

| Area                                                    | Status                  | Required repair                                                                                                                      |
| ------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Canadian law modules under `backend/app/ingestion/laws` | `STUB`                  | Replace placeholder sections with validated Justice Canada/provincial feeds, parser tests, legal notes, snapshots, and custody logs. |
| Web monitor police/government release adapters          | `EXPERIMENTAL` / `STUB` | Keep review-only or disabled until source terms, parser, rate limits, and snapshot proof exist.                                      |
| Portal-root sources in source YAML                      | `STUB` as automation    | Keep as `portal_reference`; do not run as machine ingestion until a machine-readable endpoint and adapter config are proven.         |
| Legacy Leaflet route                                    | `REMOVED`               | MapLibre is now canonical at `/map`; legacy `/map-v2` route has been removed.                                                        |
| Memory semantic search                                  | `EXPERIMENTAL`          | Keep derivative only. Add embeddings/search proof before exposing as a supported feature.                                            |
| memvid sidecar                                          | `EXPERIMENTAL`          | Add optional export bridge only; never make it canonical storage.                                                                    |
| AI review/checks UI                                     | `EXPERIMENTAL`          | Ensure all labels say reviewer-assistance/rule-based unless a validated model provider is configured.                                |
| Workspace root `.sln`                                   | `DEAD`                  | Keep only as historical/editor artifact or remove in a cleanup milestone.                                                            |
| Frontend e2e tests                                      | `STUB`                  | No e2e test suite exists yet. Not a release blocker for alpha gate; required before beta.                                            |
| Public API boundary tests                               | `PARTIAL`               | Phase 10 tests probe key exclusion rules (rejected/quarantined/AI-only). Full coverage is an ongoing effort.                         |

## Policy

- A stub must fail closed.
- A placeholder must not be enabled by configuration defaults.
- A source without legal notes and parser proof must not be marked `machine_ingest`.
- A derived memory/search artifact must not be presented as canonical evidence.
- AI outputs are reviewer assistance only — they are not legal determinations or guilt assessments.
