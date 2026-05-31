<!-- markdownlint-disable -->

# Future Architecture

Status: PLANNING — strategic roadmap and implementation plan

This document describes the strategic roadmap for JUDGE_ATLASX evolution from the current document-centric alpha to a claim-centric, evidence-governed intelligence platform. It includes both the strategic 10-phase roadmap and detailed planning for future capabilities.

---

## Strategic Roadmap Overview

### Mission Statement
JUDGE_ATLASX is an evidence-governed Canadian legal intelligence platform that transforms raw legal documents into structured claims, entities, and temporal graphs while maintaining strict evidence authority and AI-derivative boundaries.

### System Evolution
**Current State (Alpha):** Documents → Search → Review → Display
**Target State (v1.0):** Evidence → Claims → Entities → Events → Graph → Reasoned Retrieval

### 10-Phase Strategic Plan

| Phase | Name | Duration | Status | Dependencies |
|-------|------|----------|--------|--------------|
| Phase 1 | Stabilize Foundation | 4-7 weeks | Phase 1A Complete | None |
| Phase 2 | Canonical Data Model | 2-4 weeks | Complete | Phase 1 |
| Phase 3 | Ingestion Hardening | 2-4 weeks | Partial | Phase 1, 2 |
| Phase 4 | Temporal Graph System | 4-6 weeks | Partial | Phase 2, 5 |
| Phase 5 | Retrieval Intelligence | 4-6 weeks | Partial | Phase 1, 2 |
| Phase 6 | Human Review Architecture | 3-4 weeks | Partial | Phase 1, 2 |
| Phase 7 | Public Interface | 4-6 weeks | Partial | Phase 6 |
| Phase 8 | Entity Resolution Engine | 6-8 weeks | Partial | Phase 5 |
| Phase 9 | National Scaling | 8-12 weeks | Not Started | Phase 8 |
| Phase 10 | Long-Term Intelligence Layer | 8-12 weeks | Not Started | Phase 8 |

### Phase Completion Status

**Phase 1 (Stabilize Foundation):**
- ✅ Phase 1A: Repository cleanup and boundary enforcement (completed May 16, 2026)
- ⚠️ Phase 1B: Infrastructure hardening (Redis, object storage, vector DB) - IN PROGRESS
- ⚠️ Phase 1C: Evidence vault operations (replay, lineage, integrity) - PENDING

**Phase 2 (Canonical Data Model):**
- ✅ Complete - 8 canonical entities locked (May 16, 2026)
- ✅ Database schema with 50+ alembic migrations
- ✅ Immutability rules and constraints enforced

**Phase 3 (Ingestion Hardening):**
- ✅ Adapter contracts with parser_version immutability
- ✅ Source registry with automation status gating
- ❌ Redis caching layer (Phase 1B dependency)
- ❌ Object storage for large files (Phase 1B dependency)

**Phase 4 (Temporal Graph System):**
- ✅ Temporal fields in legal sections
- ✅ Temporal reasoner module exists
- ❌ Time-travel queries not exposed in API
- ❌ Graph traversal optimizations not implemented

**Phase 5 (Retrieval Intelligence):**
- ✅ Evidence vault with snapshot integrity
- ✅ MemoryClaim with evidence linkage
- ❌ Semantic search disabled (embeddings_enabled=false)
- ❌ No vector database backend (Phase 1B dependency)

**Phase 6 (Human Review Architecture):**
- ✅ ReviewItem table with status transitions
- ✅ Review queue API endpoints
- ❌ JWT authentication disabled by default
- ❌ No RBAC system (roles, permissions)

**Phase 7 (Public Interface):**
- ✅ Next.js 14 frontend with TypeScript
- ✅ Map components and entity detail views
- ❌ No public correction/takedown system
- ❌ No public API documentation

**Phase 8 (Entity Resolution Engine):**
- ✅ CanonicalEntity table with merge tracking
- ✅ Entity resolution module exists
- ❌ Entity resolution not automated (manual only)
- ❌ No fuzzy matching algorithms

**Phase 9 (National Scaling):**
- ❌ Not Started - Canada-only, no multi-jurisdiction support

**Phase 10 (Long-Term Intelligence Layer):**
- ✅ AI modules exist (claim extraction, contradiction detection)
- ❌ AI not integrated with production workflows
- ❌ No AI drift detection
- ❌ No claim salience scoring

---

## Target Final Architecture

### Claim-Centric Data Model
- **Evidence Layer:** Immutable SourceSnapshots with hash verification
- **Claim Layer:** MemoryClaims extracted from evidence, non-authoritative
- **Entity Layer:** CanonicalEntities with deduplication and merge tracking
- **Relationship Layer:** RelationshipEvidence with provenance and confidence
- **Temporal Layer:** Valid_from/valid_to fields for time-travel queries
- **Graph Layer:** Multi-hop traversal with influence scoring

### Evidence Governance Rules
1. **Evidence is Authoritative:** All claims must trace to SourceSnapshot
2. **AI is Derivative:** AI outputs are suggestions only, never auto-applied
3. **No Autonomous Accusation:** AI cannot create legal records or make publication decisions
4. **Publication Requires Review:** Public visibility requires human approval
5. **Immutable Audit Trail:** AuditLog is append-only with chain integrity

### Technical Risks and Mitigations

**Graph Poisoning:**
- Risk: Malicious actors inject false relationships
- Mitigation: Evidence-required policy, manual review for high-confidence edges, minimum evidence threshold (2 sources)

**AI Drift:**
- Risk: AI models drift from ground truth over time
- Mitigation: Non-authoritative marker, manual review before publication, periodic model retraining, claim salience decay

**Scaling Review:**
- Risk: Review queue overwhelms human reviewers
- Mitigation: Automated triage, confidence-based routing, review analytics, escalation workflows

**Legal Exposure:**
- Risk: Incorrect information causes legal liability
- Mitigation: Evidence-authoritative rule, correction/takedown system, jurisdiction-specific privacy rules, legal review of public features

---

## Implementation Policy

> Features listed in this document **must not** be implemented piecemeal without:
>
> 1. A corresponding entry in the completion checklist for the phase
> 2. A policy review for any feature that touches publication decisions or PII
> 3. A sprint plan approved before coding begins
> 4. Proof gate validation before merging to main
>
> Partial stubs for unimplemented features **must** carry a `NOT_IMPLEMENTED` comment at module top level.

---

## Detailed Future Capabilities

The sections below describe specific capabilities that are explicitly **not present** in the current codebase or are only partially implemented.

---

## 1. Semantic Search

**Status**: NOT_IMPLEMENTED  
**Config gate**: `JTA_EMBEDDINGS_ENABLED=true` (defaults False; heavy torch dependency)

### Planned

- Sentence-transformer embeddings (`all-MiniLM-L6-v2` or similar) over canonical entity text
- pgvector extension on PostgreSQL for vector similarity search
- Hybrid retrieval: BM25 keyword score + cosine similarity re-rank
- Expose via `GET /api/v1/search/semantic?q=...`

### Dependencies Not Yet Present

- `pgvector` PostgreSQL extension
- `sentence-transformers` Python package (guarded by feature flag)
- Embedding generation pipeline (batch + incremental)
- Vector index maintenance (incremental rebuild on new records)

### Constraints

- Embeddings must be regenerated after any canonical text normalization change
- Source-tier filtering must be applied before embedding search (no unsourced results)
- Output must include provenance metadata (which source, which snapshot, confidence score)

---

## 2. AI-Assisted Review

**Status**: NOT_IMPLEMENTED (stub routes exist in `ai_review.py`, `ai_correctness.py`, `chat.py`)  
**Config gate**: `JTA_OLLAMA_ENABLED=true` (defaults False)

### Planned

- Local LLM (via Ollama) for:
  - Suggesting review decisions on queued items
  - Flagging potential PII in ingested records
  - Confidence scoring on entity resolution
- AI suggestions must be displayed as suggestions only, never auto-applied
- All AI decisions must be logged with model version + prompt hash for audit trail

### Hard Constraints (from AI_BOUNDARY_RULES.md)

- AI cannot create, modify, or delete legal records
- AI cannot make publication decisions
- AI outputs are advisory only and require human review confirmation
- AI subsystem operates in a read-only context; no write access to case/judge/defendant tables

---

## 3. Graph Intelligence

**Status**: Partial infrastructure (graph routes exist); intelligence layer NOT_IMPLEMENTED

### Planned

- Multi-hop relationship traversal (judge → cases → defendants → related entities)
- Influence/centrality scoring for judge and case networks
- Timeline anomaly detection (statistically unusual sentencing patterns)
- Expose via enhanced `GET /api/v1/graph/entity/{type}/{id}/subgraph?depth=N`

### Current State

- Basic graph routes exist (`graph.py`) with entity edge queries
- No scoring, traversal algorithms, or anomaly detection implemented
- `enable_public_relationship_arcs` gate exists but requires policy sign-off

---

## 4. Cross-Jurisdiction Expansion (Beyond Saskatchewan / Federal Canada)

**Status**: NOT_IMPLEMENTED  
**Current scope**: Saskatchewan + Federal Canada sources only

### Planned Expansion (requires new source registrations + ToS verification)

- Ontario courts (CanLII + Ontario Court of Justice)
- British Columbia courts
- Alberta Queen's Bench
- Federal administrative tribunals

### Requirements Before Expansion

- Each new province requires its own `confidence_class` + `terms_verified` entries
- Separate rate-limit policy per jurisdiction
- Policy review for cross-provincial PII handling differences
- Separate `retention_policy` if provincial law differs from federal baseline

---

## 5. Public Correction and Takedown System

**Status**: NOT_IMPLEMENTED  
**Reference**: `docs/CORRECTION_AND_TAKEDOWN.md`

### Planned

- Public web form for individuals to submit correction requests
- Admin review queue for takedown/correction requests (separate from ingestion review)
- Formal response timeline (target: 14 business days per `docs/CORRECTION_AND_TAKEDOWN.md`)
- Audit log of all correction/takedown decisions

### Current Gap

- No correction request model or table exists
- Admin review queue (`admin_review.py`) handles ingestion review only
- No external-facing correction form in the frontend

---

## 6. Real-Time Ingestion (Event-Driven)

**Status**: NOT_IMPLEMENTED  
**Current model**: Polling via APScheduler (`JTA_ENABLE_SCHEDULER`)

### Planned

- Webhook receivers for sources that support push (e.g., CKAN DCAT feeds)
- Message queue (Redis Streams or similar) for fan-out to multiple consumers
- Near-real-time evidence snapshot creation on new record receipt

### Constraint

- APScheduler polling approach is correct for v1; real-time is post-v1 only

---

## 7. Multi-Tenant / Organization Accounts

**Status**: NOT_IMPLEMENTED  
**Current model**: Single-admin JWT with first-admin bootstrap

### Not Planned for v1

- Organization-scoped data views
- Role-based access control beyond admin/non-admin
- API keys per organization

---

## Implementation Policy

> Features listed in this document **must not** be implemented piecemeal without:
>
> 1. A corresponding entry in `COMPLETION_CHECKLIST.md`
> 2. A policy review for any feature that touches publication decisions or PII
> 3. A sprint plan approved before coding begins
>
> Partial stubs for unimplemented features **must** carry a `NOT_IMPLEMENTED` comment at module top level.
