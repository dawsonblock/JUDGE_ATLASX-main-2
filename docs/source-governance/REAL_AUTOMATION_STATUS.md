# Real Automation Status — Source Ingestion

**Document type**: Operational truth  
**Last updated**: 2026 (auto-derivable from `artifacts/proof/current/source_registry_status.json`)  
**Status**: Alpha — single source enabled

---

## Summary

JUDGE ATLAS currently has **26 total registered sources**, with **2 sources runnable now** and **24 sources not currently runnable**. This document records the ground truth.

| Status | Count | Description |
|---|---|---|
| `machine_ready_enabled` | 2 | Adapter exists, automation enabled, runs in production |
| `machine_ready_disabled` | 5 | Adapter exists and validated but intentionally disabled (alpha scope) |
| `adapter_missing` | 16 | Source defined in registry; no adapter implemented yet |
| `deprecated` | 3 | Source removed from active scope |
| `disabled_stub` | 1 | Placeholder only; not intended for near-term automation |

Additional generated summary fields from `source_registry_status.json`:

- `total_sources`: 26
- `machine_ingest_sources`: 8
- `runnable_now`: 2
- `enable_ready`: 5
- `deprecated`: 3

---

## Enabled Source (Production)

| Source Key | Notes |
|---|---|
| `justice_canada_laws_xml` | Justice Canada consolidated statutes XML feed. Adapter complete, snapshot + dedup active. |
| `saskatoon_open_data_public_safety` | City of Saskatoon CKAN public-safety feed. Adapter is fixture-validated and enabled for machine ingest. |

---

## Ready But Disabled (Alpha Scope)

These sources have working adapters and have passed validation. They are disabled to keep the alpha release scope narrow and auditable. Re-enabling requires a documented decision and proof run.

| Source Key | Reason Disabled |
|---|---|
| `scc_decisions` | Alpha scope reduction |
| `federal_court_canada` | Alpha scope reduction |
| `sk_courts_qb_decisions` | Alpha scope reduction |
| `sk_courts_ca_decisions` | Alpha scope reduction |
| `sk_legislature_hansard` | Alpha scope reduction |

---

## Adapter Not Yet Implemented

16 sources are defined in the source registry but have no adapter code. These exist to document intent and future roadmap, not to claim automation capability.

See `backend/app/ingestion/sources/` for the registry definitions and `backend/app/ingestion/source_adapters/` for existing adapters.

---

## What "Automated" Means Here

A source is `machine_ready_enabled` only when ALL of the following hold:

1. An adapter class exists in `backend/app/ingestion/source_adapters/`
2. The adapter passes its contract test (`tests/backend/test_machine_ingest_contract.py`)
3. The source's `ingestion_mode` is `machine_ingest` in the source registry
4. The `automation_status` field is `machine_ready_enabled`
5. The source has produced at least one committed snapshot in the evidence vault
6. The proof pipeline (`make proof`) passes with this source included

---

## Governance

This document must be updated whenever:
- A source moves from `machine_ready_disabled` → `machine_ready_enabled`
- A new adapter is completed and passes contract tests
- A source is deprecated or removed

Changes require a new `make proof` run and a proof artifact update before commit.
