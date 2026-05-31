# Source Registry

This document is the canonical policy reference for source governance in alpha.

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

## Allowed Source States

- `machine_ingest`
- `portal_reference`
- `manual_upload`
- `disabled_stub`
- `deprecated`

## Machine Ingest Requirements

A source may be `machine_ingest` only when all requirements hold:

- adapter exists in runtime adapter registry
- adapter provides real raw snapshot bytes
- adapter provides fetch URL
- parser version matches registry
- source key matches registry
- replay test exists
- parser contract test exists

## Publication Guardrails

- no public claim without linked evidence snapshot and review state
- evidence is authoritative
- AI/memory outputs are derivative only

## Legacy U.S. Route Isolation

- Legacy U.S.-focused ingestion endpoints are quarantined behind
	`JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true` and are unmounted by default.
- Default alpha posture is Canada-first ingestion only.
- Quarantined routes are outside current Canada-first alpha coverage and do not
	alter source registry runnable counts unless explicitly enabled and re-proved.

See coverage matrix at `docs/source-governance/COVERAGE_MATRIX.md`.
