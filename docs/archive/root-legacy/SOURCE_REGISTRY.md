# SOURCE REGISTRY

This document describes the source registry model, its current state, and the
rules governing source lifecycle in JUDGE_ATLAS.

---

## Registry Location

The canonical source registry is defined in:

```
backend/app/sources/registry.json
```

Runtime verification is performed by:

```
python scripts/verify_source_registry.py
python scripts/verify_source_registry.py --json
```

A JSON snapshot of the registry state is written to:

```
artifacts/proof/current/source_registry_status.json
```

---

## Source Lifecycle States

| State | Meaning |
|---|---|
| `runnable_disabled` | Adapter and parser are implemented; operator `/enable` required before running |
| `portal_reference` | Data is available only via a web portal; no machine-ingestable adapter exists |
| `disabled_stub` | Placeholder entry; no adapter written |
| `deprecated` | Superseded by another source_key; references should be migrated |
| `manual_reference` | Human-readable reference only; never an ingestable data source |

---

## Automation States

| State | Meaning |
|---|---|
| `machine_ready_disabled` | Adapter is implemented but the source has not been `/enable`d |
| `adapter_missing` | No adapter has been written for this source |
| `disabled_stub` | Source is a stub with no implementation |

---

## Source Tiers

Sources are classified by trust tier. Higher tiers produce evidence that can
support canonical legal facts; lower tiers provide secondary context only.

| Tier | Type | Examples |
|---|---|---|
| 1 | Court record, judgment, order, appeal decision | Federal Court, SCC, CourtListener/RECAP |
| 2 | Official government or prosecutor release | Saskatchewan Ministry of Justice |
| 3 | Official police or city open-data portal | Saskatoon Police open data |
| 4 | Reputable news article | Secondary context only |
| 5 | User submission | Pending moderator review |

---

## Source Rules

- A source at tier 4 (news) cannot by itself create a verified legal outcome.
- Repeat-offender language must remain indicator-based unless a tier-1 or tier-2
  source explicitly supports the legal fact.
- Deprecated sources must not be used for new ingestion runs. Migrate to the
  canonical replacement source_key.
- Portal-reference sources are reference entries only and cannot be scheduled
  for automated ingestion.
- Every enabled source must pass `validate_sources` before an ingestion run is
  allowed to start.

---

## Current Registry Summary

See `artifacts/proof/current/source_registry_status.json` for the current
machine-generated snapshot, and `docs/SOURCE_REGISTRY_STATUS.md` for the
human-readable table view regenerated at proof time.

Key current facts (as of last proof run):

- Total configured sources: 26
- Machine-ingest sources ready to enable: 7
  (`justice_canada_laws_xml`, `federal_court_canada`, `scc_decisions`,
  `sk_courts_qb_decisions`, `sk_courts_ca_decisions`, `sk_legislature_hansard`,
  and one other)
- Deprecated sources requiring migration: 3
  (`scc_judgments` → `scc_decisions`;
   `federal_court_canada_decisions` → `federal_court_canada`;
   `canada_justice_laws` → `justice_canada_laws_xml`)
- Portal-reference sources (no adapter): 9
- Disabled stubs (no adapter): 4

---

## Enabling a Source

1. Confirm the source URL is reachable and the terms of use permit automated
   ingestion.
2. Confirm the adapter and parser are present and return `adapter_state != "missing_parser"`.
3. Use the admin panel `/enable` action or the CLI `judgectl source enable <key>`.
4. Schedule an initial ingestion run and review the first batch of records before
   enabling public visibility.
