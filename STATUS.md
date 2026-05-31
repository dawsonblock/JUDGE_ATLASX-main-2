# STATUS

> [!WARNING]
> Manual source ZIPs (e.g., `JUDGE_ATLASX-main N.zip`, `workspace_snapshot.zip`) are **NOT authoritative release artifacts**. Only `dist/JUDGE_ATLAS-main-final.zip` produced by the canonical build pipeline may be distributed.

**Repository**: JUDGE_ATLASX-main
**Current release status**: alpha release posture; see canonical gate
**Alpha gate checks**: see artifacts/proof/current/release_gate.json
**Production ready**: false
Production ready: FALSE

> [!WARNING]
> Production-ready=false until all production gates pass.

This repository is an alpha platform and not approved for production deployment.
This repository is an alpha/research-grade platform, not a production legal system.

## Canonical Proof

- **Proof location**: `artifacts/proof/current/CURRENT_PROOF.md`
- **Release readiness**: `artifacts/proof/current/release_readiness.md`
- **Machine truth**: `artifacts/proof/current/release_gate.json`
- **Alpha posture summary**: `artifacts/proof/current/CURRENT_ALPHA_STATUS.md`
- node_version: v22.22.3
- npm_version: 10.9.8

## Current State

- Evidence storage is authoritative; memory and AI outputs are derivative.
- Legal correlations are hypotheses, not verdicts.
- Source ingestion is disabled by default.
- Manual review is required before public publication.
- Source coverage is incomplete.
- Alpha proof status: derive from artifacts/proof/current/release_gate.json.
- Alpha readiness status: derive from artifacts/proof/current/release_readiness.md.

## What's Tested

- The canonical test/proof inventory is recorded in artifacts/proof/current/CURRENT_PROOF.md.
- Do not treat this file as a substitute for release_gate.json or release_readiness.md.

## What's Not Ready for Production

- Live-source coverage is partial
- Complete Canadian legal coverage claim is not validated
- Production deployment environment is not tested
- Production operational readiness is not certified

## Gate Interpretation

- Alpha gate truth is defined only by artifacts/proof/current/release_gate.json.
- Release readiness truth is defined only by artifacts/proof/current/release_readiness.md.
- Human-readable summaries must not override the canonical proof artifacts.
- Production readiness remains false by design for this alpha scope.

## Status Matrix

- authority: artifacts/proof/current/release_gate.json
- alpha_ready: true
- production_ready: false
- public_release_safe: false
- ingestion_coverage: 2/26 runnable sources (from canonical source-registry proof)
- AI_answering_enabled: true (derivative, evidence-cited alpha mode)
- workflow_admin_enabled: false (gated/experimental)
- live_map_enabled: false (gated)

## Known Constraints

- Review approval required before public output
- Source-dependent coverage model
- Manual triage required for complex correlations
- Alpha status: this platform may undergo breaking changes

## Next Steps

1. Run `make proof` to regenerate proof artifacts
2. Validate changes with `python3 scripts/check_proof_consistency.py`
3. Build release archive with `python3 scripts/build_release_archive.py`

---

**For detailed proof metadata**, see `artifacts/proof/current/CURRENT_PROOF.md`.

---

> **Release integrity**: The only authoritative release archive is `dist/JUDGE_ATLAS-main-final.zip`. Do not ship manually zipped working trees. `release_gate.json` is only valid as a proof artifact when every log path it references exists inside `artifacts/proof/current/` at packaging time.
