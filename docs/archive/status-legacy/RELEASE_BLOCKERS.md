# Release Blockers

<!-- Maintained as a release gate. A release candidate requires all items
below to be resolved and checked (☑). Items are organised by phase.
Phases marked DONE have all checks passing. -->

_Last updated: 2026-05-06_

Alpha gates pass; beta blockers remain until all unchecked phases below are complete.

---

## Phase 0 — Establish proof baseline ✅ DONE

- [x] `scripts/proof_repo.sh` created and executable
- [x] `.github/workflows/quality-gate.yml` updated to upload `artifacts/proof/latest/`

---

## Phase 1 — Make repo status truthful

- [x] `CURRENT_STATUS.md` external/ reference-only declaration added
- [x] `CURRENT_STATUS.md` source register states enumerated
- [x] `CURRENT_STATUS.md` memory=derivative declared
- [x] `CURRENT_STATUS.md` AI=citation-bounded declared
- [x] `REPO_REALITY.md` adapter source-state classification table added
- [x] `docs/RELEASE_BLOCKERS.md` created (this file)
- [x] `scripts/check_truth_claims.py` BANNED_PHRASES extended with Phase 1 phrases
- [x] `docs/history/` created; stale "done" docs archived

---

## Phase 2 — Lock relationship arcs ✅ DONE

- [x] `RelationshipArcPolicy` with `enable_public_relationship_arcs` config flag
- [x] Causal label filter, evidence count floor, pagination cap enforced
- [x] `JudgeRelationshipArcs.tsx` checks `arcs_enabled` flag
- [x] 8/8 policy tests passing

---

## Phase 3 — Harden evidence immutability ✅ DONE

- [x] `evidence_integrity.py` with `verify_snapshot_integrity`, `record_custody_event`, `assert_snapshot_append_only_change`
- [x] SQLAlchemy `before_update` hook blocks mutation of immutable fields
- [x] 17/17 integrity tests passing

---

## Phase 4 — Machine-ingest contract gate ✅ DONE

- [x] `ContractViolationError` + `validate_record_contract()` in `adapters.py`
- [x] `source_runner.py` quarantine gate for contract-violating records
- [x] 16/16 contract tests passing

---

## Phase 5 — SSRF / domain safety ✅ DONE

- [x] `security/safe_fetch.py` with SSRF, redirect, scheme, content-type guards
- [x] Re-check on every redirect target
- [x] 16/16 safe-fetch tests passing

---

## Phase 6 — Auth / RBAC / audit

- [ ] `tests/helpers/auth_matrix.py` created with `AuthMatrixCase`, `assert_auth_matrix`, `make_jwt_for_role`
- [ ] `test_mutation_rbac_matrix.py` covers all admin mutation routes
- [ ] Legacy shared-token path rejected in production mode
- [ ] Audit log written on every mutation (test-verified)
- [ ] CI route-count vs matrix-coverage gate added to `quality-gate.yml`

---

## Phase 7 — Source truth visible

- [ ] `SourceStatus` enum added to `statuses.py` or new `source_status.py`
- [ ] `SourceRegistry` model has `source_status` column + Alembic migration
- [ ] Admin source endpoint exposes all required fields
- [ ] Public source endpoint exposes safe subset
- [ ] 5+ source-visibility tests passing

---

## Phase 8 — Frontend proof and API contracts

- [ ] `npm run typecheck` and `npm run build` pass with zero suppressed errors
- [ ] `frontend/lib/types/contracts.ts` created with shared DTO interfaces
- [ ] `frontend/lib/api.ts` updated to use `contracts.ts` types
- [ ] Smoke tests: empty-state renders, `arcs_enabled=false` stays null, API-failure fallback
- [ ] `nextjs.yml` enforces typecheck + build pass

---

## Phase 9 — AI and memory bounded

- [ ] `test_ai_citation_bounds.py` — 6 tests: no-citation output rejected, guilt/danger/corruption task rejected, contradicted memory marked disputed
- [ ] No AI function returns publishable verdict/guilt/danger/corruption score without `requires_human_review: true`
- [ ] `docs/AI_LIMITATIONS.md` matches actual behaviour

---

## Phase 10 — Final release gate

- [ ] `docs/RELEASE_GATE.md` created
- [ ] `scripts/release_gate.sh` created; reads `artifacts/proof/latest/proof_summary.md`; exits 1 on any FAIL
- [ ] CI `quality-gate.yml` runs `release_gate.sh --dry-run` on every PR
- [ ] All phases above show ✅ DONE
