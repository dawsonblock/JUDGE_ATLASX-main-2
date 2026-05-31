# Frontend Dependency Exceptions (High/Critical)

This document is required when frontend audit reports high or critical vulnerabilities.
Each package entry must include:
- package
- version
- vulnerability ID
- reason it is not exploitable in this app
- mitigation
- expiry date
- owner

## Exception Entries

### `glob`
- **Package**: glob
- **Version**: transitive via eslint-config-next / @next/eslint-plugin-next (see frontend/package-lock.json)
- **Vulnerability ID**: GHSA-5j98-mcp5-4vw2
- **Reason it is not exploitable**: JUDGE_ATLAS does not execute glob CLI `-c/--cmd`; usage is limited to developer/CI lint tooling and not exposed to runtime user input.
- **Mitigation**: Keep lint/build isolated to trusted CI runners, pin Node 20 in gates, and upgrade upstream dependency chain when patched release is available.
- **Expiry date**: 2026-07-31
- **Owner**: security-review-alpha

### `@next/eslint-plugin-next`
- **Package**: @next/eslint-plugin-next
- **Version**: transitive via eslint-config-next (see frontend/package-lock.json)
- **Vulnerability ID**: GHSA-5j98-mcp5-4vw2 (via glob)
- **Reason it is not exploitable**: Dependency is used for linting only; no runtime request path reaches this package in production serving path.
- **Mitigation**: Track upstream eslint-config-next / Next.js releases and upgrade once compatible patched chain is available.
- **Expiry date**: 2026-07-31
- **Owner**: security-review-alpha

### `eslint-config-next`
- **Package**: eslint-config-next
- **Version**: current repository-pinned dev dependency (see frontend/package.json)
- **Vulnerability ID**: GHSA-5j98-mcp5-4vw2 (transitive via @next/eslint-plugin-next -> glob)
- **Reason it is not exploitable**: Used at build/lint time only and not loaded in request-time runtime.
- **Mitigation**: Upgrade to patched major release once compatibility validation completes.
- **Expiry date**: 2026-07-31
- **Owner**: security-review-alpha

### `next`
- **Package**: next
- **Version**: repository pinned version in frontend/package.json
- **Vulnerability ID**: GHSA-9g9p-9gw9-jx7f, GHSA-8h8q-6873-q5fj, GHSA-c4j6-fc7j-m34r, GHSA-36qx-fr4f-26g5
- **Reason it is not exploitable**: Current alpha deployment does not expose vulnerable image-optimization path publicly, does not use websocket upgrade path, and does not enable i18n middleware bypass conditions.
- **Mitigation**: Maintain gateway/auth boundary controls and upgrade to patched Next.js version in beta hardening window.
- **Expiry date**: 2026-07-31
- **Owner**: security-review-alpha
