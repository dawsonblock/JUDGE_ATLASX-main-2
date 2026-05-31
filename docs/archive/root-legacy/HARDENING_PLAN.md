# HARDENING PLAN

## Wave 1: Governance Baseline
- Add explicit system boundary and limitation docs.
- Add executable verification tools for evidence, audit, and source contracts.
- Status: in progress.

## Wave 2: Enforcement Expansion
- Route all mutation endpoints through JWT role checks.
- Tighten source-run gating and quarantine semantics.
- Status: in progress.

## Wave 3: CI Proof Gates
- Enforce verification CLIs and critical tests in CI/release checks.
- Publish reproducible proof artifacts per release candidate.
- Status: pending.

## Wave 4: Documentation Reconciliation
- Keep status docs aligned with real implemented state.
- Mark partial/placeholder areas explicitly.
- Status: pending.
