# Evidence Model

Canonical evidence model for alpha runtime.

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

## Authority Rule

Evidence snapshots are authoritative. AI and memory outputs are derivative only.

## Snapshot Requirements

- stored in evidence root outside repository
- content-addressed by SHA256
- stored hash must match computed hash
- snapshot blobs are immutable after write

## Publication Rule

No public record may be shown without:

- approved review state
- at least one linked evidence snapshot

## Validation Commands

- `python3 scripts/verify_evidence_store.py`
- `python3 scripts/verify_snapshot_hashes.py`
- `python3 scripts/find_orphan_snapshots.py`
