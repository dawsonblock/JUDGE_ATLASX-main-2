# JUDGE_ATLASX

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

## What It Is

A proof-gated alpha runtime for evidence-linked legal-intelligence workflows with source governance, review gates, and auditability.

## What It Is Not

It is not an autonomous accusation engine, predictive policing system, or production legal authority.

## Alpha Warning

This repository is alpha only. Do not treat outputs as legal determinations.

## Quickstart

```bash
make setup
make dev
```

## Test Command

```bash
make test
```

## Proof Command

```bash
make proof
```

## Source Coverage Link

See `docs/source-governance/COVERAGE_MATRIX.md`.

## Security Warning

Evidence is authoritative. AI and memory outputs are derivative only. Public visibility requires review approval and linked evidence snapshot.

## Canonical Status And Proof References

- STATUS.md
- artifacts/proof/current/release_gate.json
- artifacts/proof/current/CURRENT_PROOF.md
- artifacts/proof/current/release_readiness.md

## Release Artifact Policy

> [!WARNING]
> Manual source ZIPs (e.g., `JUDGE_ATLASX-main N.zip`, `workspace_snapshot.zip`) are **NOT authoritative release artifacts**. Only `dist/JUDGE_ATLAS-main-final.zip` produced by the canonical build pipeline may be distributed.

- Authoritative release archives are produced only by scripts/package_and_validate_release_archive.sh.
- Raw source snapshot ZIP files are not distributable release artifacts.
- Publish only dist/JUDGE_ATLAS-main-final.zip and include its SHA-256 in release communication.
- Do not upload workspace/source snapshots (for example JUDGE_ATLASX-main N.zip) as release candidates.
- See docs/RELEASE_READINESS.md and docs/reports/HARDENING_RELEASE_ARTIFACT_CHAIN.md.

## Canonical Release Commands

```bash
make proof
bash scripts/package_and_validate_release_archive.sh \
  --archive-path dist/JUDGE_ATLAS-main-final.zip \
  --package-root-name JUDGE_ATLAS-main
```
