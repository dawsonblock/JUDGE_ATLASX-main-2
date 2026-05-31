# RELEASE_BLOCKERS

## Alpha Gate Status

> [!WARNING]
> Manual source ZIPs (e.g., `JUDGE_ATLASX-main N.zip`, `workspace_snapshot.zip`) are **NOT authoritative release artifacts**. Only canonical archives produced by the release pipeline may be distributed.

- Source-of-truth blocker state is defined by artifacts/proof/current/release_gate.json.
- Source-of-truth readiness narrative is defined by artifacts/proof/current/release_readiness.md.
- Canonical status file is STATUS.md.
- Canonical current proof summary is artifacts/proof/current/CURRENT_PROOF.md.
- Alpha gate pass/fail is not a production readiness claim.

## Current Blocker Policy

- Treat release_gate.json as the only authoritative blocker source.
- Treat release_readiness.md as the only authoritative blocker narrative.
- Manual summaries in this file must never mark phases PASS unless the canonical artifacts say so for the current run.
- If artifacts/proof/current/release_gate.json and this file disagree, the gate wins.

Production-ready=false until all production gates pass.

## Status Matrix

- authority: artifacts/proof/current/release_gate.json
- alpha_ready: true
- production_ready: false
- public_release_safe: false
- ingestion_coverage: 2/26 runnable sources (from canonical source-registry proof)
- AI_answering_enabled: true (derivative, evidence-cited alpha mode)
- workflow_admin_enabled: false (gated/experimental)
- live_map_enabled: false (gated)

Historical repair/blocker notes were moved to docs/history/2026-05-27-repair-blocker-notes.md.

## Status Assertion

- release_status: derive from artifacts/proof/current/release_gate.json
- production_ready: false
- operational_posture: alpha

## Interpretation

- Current alpha release state must be read from the canonical gate artifacts for the current run.
- Deferred scope items are non-blocking only when the current canonical gate artifacts say the alpha gate passed.

---

> **Release integrity**: The only authoritative release archive is `dist/JUDGE_ATLAS-main-final.zip`. Do not ship manually zipped working trees. `release_gate.json` is only valid as a proof artifact when every log path it references exists inside `artifacts/proof/current/` at packaging time.
