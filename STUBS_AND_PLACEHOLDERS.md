# STUBS_AND_PLACEHOLDERS

## Incomplete Features / Placeholders

### Backend

#### Routes

- `backend/app/api/routes/live_map.py` — **Experimental and unmounted** (do not mount without auth boundary tests)
- `backend/app/api/routes/workflow_admin.py` — **Experimental and unmounted** (do not mount without admin/source_admin auth tests)
- Memory query system (`/api/memory/*`) — **Shallow implementation** (only observation, status, limit; missing subject/predicate/object detail, match_reason, salience)

#### Services

- `MemoryQuery` — **Limited scope** (no temporal query operators; basic confidence threshold only)
- `MemoryHit` model — **Lossy extraction** (loses evidence reference detail, match reasoning, source tracking)
- `EventOrigin` enum — **Incomplete** (covers RuntimeLoop, Evaluator, ClaimStore, ToolGate, ProofHarness; missing external integrations)
- `RuntimeStepResult` — **Missing fields** (no answer_basis, answer_warnings, answer_confidence, cited IDs)
- `AnswerBasisItem` — **UI bridge layer only** (not integrated into runtime-core; memory crate only)

#### Database Schema

- **No bi-temporal support** (valid_from/valid_to, tx_from/tx_to fields not implemented)
- **No temporal helpers** (get_legal_section_as_of, get_claims_as_of not implemented)
- No supersedes/superseded_by relationships yet

### Frontend

- **Memory UI** — Not yet built (AnswerBasis visualization pending)
- **Advanced timeline views** — Not yet implemented
- **Live map (live_map route)** — Experimental, unmounted
- **Workflow admin UI (workflow_admin route)** — Experimental, unmounted

### Infrastructure

- **Multi-region failover** — Not implemented (single deployment only)
- **High-availability PostgreSQL setup** — Not in core deployment
- **Redundant evidence storage** — Single-backend only

### Documentation

- `docs/HARDENING_REPORT_CODEX_MAIN_12.md` — **Not yet generated** (after main-8 cleanup complete)
- `docs/REPO_INVENTORY.md` — **Proof numbers are stale** (requires regeneration after proof run)

### Integration

- **Bi-temporal foundation** — Deferred to Phase 14 (post-alpha)
- **Advanced memory persistence** — Claim-table-only; full memory_records table not implemented
- **Cross-source evidence correlation** — Basic; no advanced hypothesis generation yet

---

## Intentional Limitations (Current Alpha)

### By Design

- **Source ingestion disabled by default** — Must be explicitly enabled per source
- **Auto-publication disabled** — All sources default to manual review
- **No autonomous verdict generation** — AI outputs are hypotheses only, not authoritative
- **Manual review required** — All public releases require human approval
- **Incomplete source coverage** — 26 sources registered; 2 actively runnable (justice_canada_laws_xml, saskatoon_open_data_public_safety); 5 enable-ready sources
- **No live legal sync** — Sources are static snapshots; real-time updates not implemented

### Known Incomplete Areas

- **Evidence correlation** — Basic cross-reference; no inference engine
- **Temporal queries** — No as-of queries; only current state available
- **Multi-language support** — English/French legal docs only; no translation
- **Accessibility** — Frontend a11y compliance pending (WCAG 2.1 AA not yet verified)
- **Performance optimization** — No query caching, pagination, or index optimization

---

## Tracked for Future Implementation

### Post-Alpha (Bi-temporal, Phase 14)

- Add temporal validity fields to 6 core models (LegalInstrument, LegalSectionRevision, SourceSnapshot, MemoryClaim, RelationshipEvidence, LegalCorrelation, GeoLegalEvent)
- Implement temporal query helpers
- Add transaction-time correction support
- Add retroactive amendment handling
- Add delayed coming-into-force scenarios

### Post-Main-8 (Next Feature Cycle)

- Memory persistence layer expansion
- EventOrigin enum extension
- RuntimeStepResult enrichment with answer basis metadata
- Live map route security validation and mounting
- Workflow admin route auth tests and public API boundary verification

---

## Definition: Placeholder vs. Incomplete

| Type | Definition | Example |
|------|-----------|---------|
| **Stub** | Code exists, not called or used yet | `live_map.py` (unmounted route) |
| **Placeholder** | Minimal implementation; full feature pending | `MemoryQuery` (shallow query operators) |
| **Incomplete** | Partially implemented; known blockers | Bi-temporal schema (deferred to Phase 14) |
| **In-progress** | Active development; not yet shipped | Memory UI frontend (awaiting backend integration) |

---

**None of these incompleteness items are release-blocking for alpha status.**  
**All are explicitly deferred or marked as non-production.**
