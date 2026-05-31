# Source Registry Contract

Machine ingestion is fail-closed. New sources must start inactive and require manual review.

## Source Classes

- `machine_ingest`: may run only when every runtime gate passes.
- `portal_reference`: reference only; never runs.
- `manual_reference`: manual evidence reference only; never runs.
- `disabled_stub`: placeholder or incomplete integration; never runs.

## Runtime Gates

A runnable source must have:

- `is_active=true`
- `source_class=machine_ingest`
- `lifecycle_state=runnable`
- `automation_status=machine_ready_enabled`
- registered `parser`
- non-empty `parser_version`
- non-empty safe `allowed_domains`
- safe `base_url`
- `requires_manual_review=true`
- `public_publish_default=false` except explicit safe aggregate/statistical sources

`seed_source_registry()` and `repair_canada_first_defaults()` validate all machine-ingest specs before touching the database. Invalid YAML fails even if a row already exists.

## Justice Canada XML

The Justice Canada XML adapter is the canonical current machine-ingest path. It should be enabled only after its registry row has valid parser metadata, safe domains, active state, runnable lifecycle, and manual review enabled.

Justice Canada ingest creates private `pending_review` legal instruments with raw snapshots. Admin publication is a separate decision that requires a snapshot content hash.

## Adding Sources

Do not add a new external data source until the current Justice Canada path remains impossible to publish incorrectly under tests. New sources should be added inactive, manual-review required, and with `public_publish_default=false`.
