# EVIDENCE LINEAGE

## Canonical Chain
1. Acquire source payload under governed source definition.
2. Normalize and write immutable `SourceSnapshot` with deterministic content hash.
3. Link derived records back to snapshot ID/hash.
4. Record review and publication decisions in audit logs.

## Integrity Rules
- Snapshot content hash must match persisted normalized payload.
- Immutable fields (hash/provenance/lineage pointers) are protected from in-place mutation.
- Integrity verification must fail closed on mismatch.

## Replay/Verification
Use the verification tooling:
- `python -m backend.tools.verify_evidence_store`
- `python -m backend.tools.verify_audit_chain`

Any failure is a release blocker.
