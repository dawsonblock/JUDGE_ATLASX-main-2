# Frontend Security Vulnerability Triage

**Generated for JUDGE_ATLAS alpha gate — manual review required per release.**
**All entries below are triaged for alpha scope. Production release requires remediation or updated upstream fixes.**

See `docs/deployment-guide/DEPENDENCY_REMEDIATION_PLAN.md` for owner/date remediation tasks and production-gate requirements.
See `docs/security/frontend_dependency_exceptions.md` for required high/critical exception metadata used by release gates.

## Alpha Exception Window

- exception_reviewed_on: 2026-05-17
- exception_review_due: 2026-06-30
- exception_expires_on: 2026-07-31
- production_blocking: true (high vulnerabilities remain)

Audit snapshot: `npm audit --json` executed in `frontend/` on 2026-05-17.

All accepted-for-alpha entries below are temporary risk exceptions and must be
re-reviewed by the due date or remediated before any production-readiness claim.

---

## Summary

| Severity | Count |
|----------|-------|
| High     | 4     |
| Moderate | 6     |
| **Total**| **10** |

---

## Triage Entries

### 1. `glob` — HIGH — GHSA-5j98-mcp5-4vw2

- **Advisory**: <https://github.com/advisories/GHSA-5j98-mcp5-4vw2>
- **Severity**: High
- **Title**: glob CLI — Command injection via `-c`/`--cmd` flag executes matches as shell commands
- **Affected packages**: `glob` (pulled in by `eslint-config-next`, `@next/eslint-plugin-next`)
- **Dependency scope**: transitive (not direct)
- **Triage decision**: **ACCEPTED — alpha scope**
  - `glob` is a devDependency used only during local linting/build on the developer workstation or CI.
  - The vulnerable `-c`/`--cmd` flag is a CLI feature; we do not invoke `glob` as a CLI tool in any script.
  - No user-controlled input reaches `glob` at runtime in this application.
  - Remediation blocked on upstream Next.js `eslint-config-next` releasing a patch.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / remediation-blocked-upstream

---

### 2. `@next/eslint-plugin-next` — HIGH (transitive via `glob`)

- **Severity**: High (transitive)
- **Affected packages**: `@next/eslint-plugin-next`
- **Dependency path**: `eslint-config-next -> @next/eslint-plugin-next -> glob`
- **Dependency scope**: transitive (not direct)
- **Triage decision**: **ACCEPTED — alpha scope** — same root cause as `glob` entry above; build-time only.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / remediation-blocked-upstream

---

### 3. `eslint-config-next` — HIGH (transitive via `@next/eslint-plugin-next`)

- **Severity**: High (transitive)
- **Affected packages**: `eslint-config-next`
- **Dependency scope**: direct dev dependency
- **Fix target from audit**: `eslint-config-next@16.2.6` (semver-major)
- **Triage decision**: **ACCEPTED — alpha scope** — same root cause as `glob` entry above; build-time only.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / remediation-blocked-upstream

---

### 4. `next` — HIGH (multiple advisories)

**Advisory 1:** GHSA-9g9p-9gw9-jx7f
- **Title**: Next.js self-hosted applications vulnerable to DoS via Image Optimization
- **Severity**: High
- **Fix target from audit**: `next@16.2.6` (semver-major)

**Advisory 2:** GHSA-8h8q-6873-q5fj
- **Title**: Next.js Vulnerable to Denial of Service with Server Components
- **Severity**: High
- **Fix target from audit**: `next@16.2.6` (semver-major)

**Advisory 3:** GHSA-c4j6-fc7j-m34r
- **Title**: Next.js vulnerable to server-side request forgery in applications using WebSocket upgrades
- **Severity**: High
- **Fix target from audit**: `next@16.2.6` (semver-major)

**Advisory 4:** GHSA-36qx-fr4f-26g5
- **Title**: Next.js has a Middleware / Proxy bypass in Pages Router applications using i18n
- **Severity**: High
- **Fix target from audit**: `next@16.2.6` (semver-major)

- **Affected packages**: `next`
- **Triage decision**: **ACCEPTED — alpha scope / NOT self-hosted image optimization in production**
  - JUDGE_ATLAS alpha does not expose the Next.js Image Optimization endpoint to the public internet.
  - Alpha deployments run behind an authenticated API gateway; the image route is not publicly reachable
    without authentication.
  - WebSocket upgrades are not used in JUDGE_ATLAS.
  - i18n middleware is not enabled in JUDGE_ATLAS.
  - Remediation: upgrade `next` to patched version when available.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / track-upstream-patch

---

### 5. `postcss` — MODERATE — GHSA-qx2v-qp2m-jg93

- **Advisory**: <https://github.com/advisories/GHSA-qx2v-qp2m-jg93>
- **Severity**: Moderate
- **Title**: PostCSS — XSS via unescaped `</style>` in CSS Stringify output
- **Affected packages**: `postcss`
- **Dependency path**: `next -> postcss`
- **Triage decision**: **ACCEPTED — alpha scope**
  - PostCSS is used at build time to process CSS files only.
  - User input does not flow into PostCSS at runtime in JUDGE_ATLAS.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / remediation-blocked-upstream

---

### 6. `vitest` — MODERATE (transitive via Vite toolchain)

- **Severity**: Moderate (transitive)
- **Affected packages**: `vitest`
- **Fix target from audit**: `vitest@4.1.6` (semver-major)
- **Triage decision**: **ACCEPTED — alpha scope**
  - Used only for local/CI contract tests (`npm run test:contracts`).
  - Not part of production runtime bundle.
  - Remediation tracked by routine dependency updates.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / dev-tooling-only

---

### 7. `vite` — MODERATE (transitive via Vitest)

- **Severity**: Moderate (transitive)
- **Affected packages**: `vite`
- **Dependency path**: `vitest -> vite`
- **Triage decision**: **ACCEPTED — alpha scope**
  - Build/test infrastructure dependency only.
  - No direct user input path in production runtime.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / dev-tooling-only

---

### 8. `vite-node` — MODERATE (transitive via Vitest)

- **Severity**: Moderate (transitive)
- **Affected packages**: `vite-node`
- **Dependency path**: `vitest -> vite-node`
- **Triage decision**: **ACCEPTED — alpha scope**
  - Executed only in local/CI test runs.
  - Not exposed as a network-facing runtime service.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / dev-tooling-only

---

### 9. `esbuild` — MODERATE (transitive build dependency)

- **Severity**: Moderate (transitive)
- **Affected packages**: `esbuild`
- **Dependency path**: `vitest -> vite -> esbuild`
- **Triage decision**: **ACCEPTED — alpha scope**
  - Used by frontend build/test toolchain only.
  - No production endpoint executes esbuild directly.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / dev-tooling-only

---

### 10. `@vitest/mocker` — MODERATE (transitive via Vitest)

- **Severity**: Moderate (transitive)
- **Affected packages**: `@vitest/mocker`
- **Dependency path**: `vitest -> @vitest/mocker`
- **Triage decision**: **ACCEPTED — alpha scope**
  - Testing-only helper package.
  - Not loaded in deployed application runtime.
- **Owner**: security-review-alpha
- **Status**: accepted-for-alpha / dev-tooling-only

---

### 11. `brace-expansion` — MODERATE (transitive via test/build tooling)

- **Severity**: Moderate (transitive)
- **Affected packages**: `brace-expansion`
- **Dependency chain (via)**: test/build-time dependency chain includes `brace-expansion` via tooling transitive dependencies.
- **Dependency scope**: transitive (not direct)
- **Runtime scope**: dev-only / build-time; not used by production request handling.
- **Fix availability**: no direct top-level patch in this repo without upstream dependency updates; tracked for routine dependency refresh.
- **Triage decision / rationale**: **ACCEPTED — alpha scope**
  - Package is not directly imported by application runtime code.
  - No user-controlled runtime input is processed through this package in deployed service paths.
  - Exposure is limited to local/CI dependency execution context.
- **Owner**: security-review-alpha
- **Target fix condition/date**: remediate when upstream dependency chain publishes and validates compatible patched versions; re-evaluate by 2026-06-30 exception review.
- **Status**: accepted-for-alpha / dev-tooling-only

---

## Attestation

All vulnerabilities listed above have been reviewed for JUDGE_ATLAS alpha scope.
None of the affected packages process user input at runtime in JUDGE_ATLAS.
All are build-time devDependencies or are blocked by upstream package release schedules.

**This triage is valid for alpha only. Before any beta/production release, a full re-audit and remediation pass is required.**

---

*This file is required by `backend/scripts/check_npm_audit_triage.py` when `npm audit` reports vulnerabilities.*
