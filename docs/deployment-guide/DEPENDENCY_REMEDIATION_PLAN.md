# Dependency Remediation Plan (Frontend Audit)

## Scope

This plan converts alpha triage outcomes into explicit remediation tasks for frontend dependency vulnerabilities.

## Current State

- `npm audit` currently reports 10 vulnerabilities.
- latest_audit_snapshot: 2026-05-17 (`frontend/`, JSON mode)
- Vulnerabilities are triaged for alpha scope in `docs/security/FRONTEND_SECURITY_TRIAGE.md`.
- Triage is not production remediation.

## Formal Alpha Exception Metadata

- reviewed_on: 2026-05-17
- review_due: 2026-06-30
- exception_expires_on: 2026-07-31
- exception_scope: alpha-only
- production_blocking: true while unresolved high vulnerabilities remain

## Production Gate Rule

No production-readiness claim is allowed while high vulnerabilities remain unresolved, unless a formal security exception is documented and approved.

## Remediation Task Matrix

| Package/Class | Severity | Dependency Path | Alpha Acceptance Reason | Affected Surface | Remediation Option | Owner | Review Due | Exception Expiry | Target Date/Release | Production Gate Status |
|---|---|---|---|---|---|---|---|---|---|---|
| glob | High | eslint-config-next -> @next/eslint-plugin-next -> glob | build-time toolchain only, no runtime CLI `--cmd` usage | lint/build tooling | upgrade via upstream Next.js ecosystem updates (`eslint-config-next@16.2.6`) | security-review-alpha | 2026-06-30 | 2026-07-31 | before beta gate | blocked until remediated/exception |
| @next/eslint-plugin-next | High | eslint-config-next -> @next/eslint-plugin-next -> glob | build-time only | lint tooling | upgrade through patched eslint-config-next release | security-review-alpha | 2026-06-30 | 2026-07-31 | before beta gate | blocked until remediated/exception |
| eslint-config-next | High | direct dev dependency | build-time only | lint tooling | upgrade to `16.2.6` and re-run lint/test/build | security-review-alpha | 2026-06-30 | 2026-07-31 | before beta gate | blocked until remediated/exception |
| next (runtime advisories set) | High | direct dependency (also drives postcss advisory chain) | alpha deployment posture, restricted exposure controls | frontend server runtime | upgrade to `next@16.2.6` and re-verify image optimization exposure | security-review-alpha | 2026-06-30 | 2026-07-31 | before beta gate | blocked until remediated/exception |
| postcss | Moderate | next -> postcss | build-time css processing only | build pipeline | upgrade transitives via Next.js upgrade | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |
| vitest | Moderate | direct dev dependency (`@vitest/mocker`, `vite`, `vite-node`) | CI/local contracts only | test tooling | upgrade to `vitest@4.1.6` plus peer stack | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |
| vite | Moderate | vitest -> vite | tooling only | test/build tooling | upgrade via vitest ecosystem to patched vite | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |
| vite-node | Moderate | vitest -> vite-node | tooling only | test tooling | upgrade via vitest/vite updates | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |
| esbuild | Moderate | vitest -> vite -> esbuild | tooling only | build tooling | consume patched esbuild via vite/vitest upgrade | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |
| @vitest/mocker | Moderate | vitest -> @vitest/mocker | tooling only | test tooling | upgrade vitest stack | security-review-alpha | 2026-06-30 | 2026-07-31 | next dependency refresh window | tracked |

## Required Update Cadence

- Re-audit `npm audit` at least once per release cycle.
- Update this matrix when advisories change.
- Record remediation completion in PRs that bump dependencies.

## Notes

- This plan does not suppress findings.
- This plan does not imply production-readiness or legal authority.
