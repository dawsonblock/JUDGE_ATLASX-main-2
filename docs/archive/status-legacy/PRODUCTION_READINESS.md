# PRODUCTION READINESS

**Current status: NOT PRODUCTION READY**

This document defines the production readiness posture for JUDGE_ATLAS and
the gates that must pass before a production deployment recommendation can be
issued.

---

## Definition of "Production Ready"

Production readiness requires ALL of the following:

1. Every gate in `scripts/proof_all_current.sh` passes and current proof
   artifacts exist in `artifacts/proof/current/`.
2. `python scripts/production_preflight.py` exits 0 (no `--expect-fail-in-dev`
   flag) against a production-like environment.
3. No open items in `RELEASE_BLOCKERS.md`.
4. Alembic migration head is current (`alembic heads` matches deployed schema).
5. JWT secret is not the default `CHANGE-ME-BEFORE-PRODUCTION` value.
6. Legacy admin-token path is disabled.
7. CORS allowlist is set to explicit origins (no wildcard).
8. Redis rate-limiting backend is configured.
9. Evidence store root is configured, exists, is writable, and resides outside
   the repository directory.
10. Debug mode is disabled.

---

## Canonical Readiness Artifacts

| Artifact | Purpose |
|---|---|
| `artifacts/proof/current/CURRENT_PROOF.md` | Canonical alpha proof receipt |
| `artifacts/proof/current/release_readiness.md` | Machine-readable readiness status |
| `artifacts/proof/current/source_registry_status.json` | Source registry snapshot |
| `artifacts/proof/current/production_preflight.md` | Preflight check output |

These artifacts must be regenerated (via `scripts/proof_all_current.sh`) before
any release recommendation is recorded. Stale artifacts are not evidence.

---

## Recommendation Ladder

| Recommendation | Minimum requirement |
|---|---|
| `blocked` | One or more release blockers open |
| `alpha-internal` | Dev environment only; no external access |
| `alpha-demo` | All alpha proof gates pass; no public data |
| `beta-candidate` | All gates pass; independent security review complete |
| `production-candidate` | All gates pass; production preflight passes; legal review complete |

Do not claim a recommendation level higher than what the current proof artifacts
support.

---

## What Is Not Yet Production-Safe

- No autonomous public publication of ingested legal records. All published
  items require human moderator approval.
- Federal law ingestion provides legal context only; it must not produce public
  map incidents.
- Crime incident data uses generalized coordinates only; exact private locations
  must never be exposed.
- Source adapters are not all runnable. See `docs/SOURCE_REGISTRY.md` and
  `artifacts/proof/current/source_registry_status.json` for current state.
- No claim of full legal authority. All content is informational only.

---

## How to Advance Readiness

1. Run `python scripts/production_preflight.py --expect-fail-in-dev` and
   address every identified blocker.
2. Resolve all items in `RELEASE_BLOCKERS.md`.
3. Run `scripts/proof_all_current.sh` and commit fresh artifacts.
4. Update `artifacts/proof/current/release_readiness.md` with the new status.

Do not update this file to claim readiness — update the proof artifacts instead.
This file describes policy; the artifacts hold the evidence.
