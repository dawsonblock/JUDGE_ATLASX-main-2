# CURRENT LIMITATIONS

## Product Limits
- Source quality depends on upstream source stability and legality of access.
- Not all jurisdictions/sources are machine-ingestable.
- Some ingestion paths remain manual or portal-reference only.

## Technical Limits
- Persisted audit-chain fields are implemented (payload hash, previous entry hash, entry hash, chain version).
- Remaining audit limitation is operational: fresh non-empty proof receipts must be regenerated for each candidate release.
- Verification tools are CLI-driven and must be wired into CI as required gates.
- Legacy admin shared-token compatibility exists for non-mutation routes; mutation hardening favors JWT roles.

## Operational Limits
- Publication throughput is bounded by reviewer capacity.
- False positives/ambiguity can still occur in extraction and must be handled in review.
- Proof artifacts can become stale; they must be regenerated for each release candidate.
- System posture remains alpha proof-gated only; not suitable for production deployment and not eligible for general release.
