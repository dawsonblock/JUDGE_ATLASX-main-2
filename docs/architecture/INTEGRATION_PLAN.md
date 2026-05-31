# THE-JUDGE Integration Plan

This document explains how the three components in this repository relate to each other and how they should be integrated over time.

## Component Roles

### JUDGE-main (The Platform)
The operational system. Contains the FastAPI backend, PostgreSQL/PostGIS database, source registry, ingestion adapters, evidence snapshots, review queue, map frontend, and `judgectl` CLI.

### CLI-Anything-main (Reference Pattern)
Contributes the **method**, not the runtime. The useful pattern is:
- Every major capability becomes a typed CLI command.
- Every command supports `--json`.
- Every command is tested through subprocess tests.
- Every command is documented in `SKILL.md`.
- Agents call commands, not random internals.

For JUDGE, this pattern becomes `judgectl`. CLI-Anything must **not** be vendored directly into the JUDGE runtime.

### memvid-Human--main (Future Archive Sidecar)
Will eventually store exported evidence, memory claims, source snapshots, or case bundles in a portable searchable `.mv2` format.

**Correct design:**
```
JUDGE writes to Postgres/PostGIS
JUDGE exports evidence/memory to JSONL
Later, JSONL can be converted into memvid .mv2 archive
```

## Integration Roadmap

### Phase 1: JSONL Export (Complete)
- `judgectl --json archive export-snapshots`
- `judgectl --json archive export-memory`
- `judgectl --json archive verify`

### Phase 2: JSONL Verification (Complete)
- Verify exported JSONL for completeness and provenance integrity.

### Phase 3: memvid Bridge (Future)
- Convert JSONL exports to `.mv2` archive format.
- Requires: memvid Python bindings or CLI wrapper.

### Phase 4: memvid Search (Future)
- Search `.mv2` archives for evidence retrieval.

### Phase 5: Archive Replay (Future)
- Replay archived evidence into a new JUDGE instance.

## What Must Never Happen
- CLI-Anything merged into JUDGE runtime
- memvid used as the primary database
- Agents directly editing the database
- Unreviewed claims auto-published
