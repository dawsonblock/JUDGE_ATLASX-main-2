# PROOF_STATUS

## Current Proof Gate Status

- Alpha gate: see artifacts/proof/current/release_gate.json.
- Release readiness: see artifacts/proof/current/release_readiness.md.
- Current proof summary: see artifacts/proof/current/CURRENT_PROOF.md.
- Individual log files are evidence artifacts, not manual status claims.

## Authority Notes

- Canonical machine truth is artifacts/proof/current/release_gate.json.
- This file summarizes proof state and must not override release_gate.json.
- Proof gate PASS, if present in canonical artifacts, indicates alpha proof-check completion only.
- production_ready remains false unless explicitly changed in canonical artifacts.
- Production-ready=false until all production gates pass.

## Runtime Environment

- **Python version**: 3.11.9
- **Node version**: v22.22.3
- **npm version**: 10.9.8
- **Platform**: macOS-26.2-arm64
- **Database**: SQLite (test), PostgreSQL (PostGIS proof)
- **Docker**: See canonical proof logs for the current run state.
- **production_ready**: false

## Proof Execution

All proof artifacts are stored under `artifacts/proof/current/` with timestamped run metadata.
Do not infer PASS from this file; read the canonical gate and current-proof outputs.

**Required proof commands:**

```bash
python3 scripts/check_path_hygiene.py
python3 scripts/check_no_generated_files.py --root .
python3 scripts/check_false_claims.py
python3 scripts/check_source_registry_docs.py
python3 scripts/check_proof_consistency.py
python3 scripts/check_proof_freshness.py
```

**Regenerate proof:**

```bash
make proof
```

## Canonical Policy

- Current release truth is derived from `artifacts/proof/current/release_gate.json`.
- Historical counts and phase narratives are non-authoritative if they conflict with canonical artifacts.
- Canonical repository posture is summarized in `STATUS.md`.

## Status Matrix

- authority: artifacts/proof/current/release_gate.json
- alpha_ready: true
- production_ready: false
- public_release_safe: false
- ingestion_coverage: 2/26 runnable sources (from canonical source-registry proof)
- AI_answering_enabled: true (derivative, evidence-cited alpha mode)
- workflow_admin_enabled: false (gated/experimental)
- live_map_enabled: false (gated)

---

**Canonical proof entry**: `artifacts/proof/current/CURRENT_PROOF.md`  
**Release readiness**: `artifacts/proof/current/release_readiness.md`

---

> **Release integrity**: The only authoritative release archive is `dist/JUDGE_ATLAS-main-final.zip`. Do not ship manually zipped working trees. `release_gate.json` is only valid as a proof artifact when every log path it references exists inside `artifacts/proof/current/` at packaging time.
