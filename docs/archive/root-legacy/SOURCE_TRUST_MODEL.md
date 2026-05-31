# SOURCE TRUST MODEL

## Source Classes
- `machine_ingest`: automated fetch/parse/snapshot pipeline.
- `portal_reference`: reference-only source, not direct ingest.
- `manual_upload`: analyst-provided material with provenance fields.
- `manual_review`: non-runnable source requiring manual handling.
- `disabled_stub`: placeholder source; not runnable.

## Automation Status
Statuses are defined by the backend automation contract and determine run eligibility.

Runnable statuses are controlled by backend constants and enforced in source validation/gating.

## Trust Principles
- Source definitions must explicitly declare review and publication defaults.
- Non-runnable classes must not be placed in runnable automation states.
- Machine-ingest sources must include governance metadata (allowed domains, legal basis, creates, cadence).
- Any contract violation must quarantine ingestion output and block normal publication flow.
