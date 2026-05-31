# Production Preflight

This document defines the separate production readiness gate for JUDGE_ATLAS.

## Scope

Production preflight is intentionally separate from alpha proof.

- Alpha proof status can be `PASS` while production preflight is `NOT PASSED` in development.
- Production readiness must remain `FALSE` until production preflight passes in a production-like environment.

## Canonical Script

Run:

- `python scripts/production_preflight.py`

Development-safe run:

- `python scripts/production_preflight.py --expect-fail-in-dev`

## Canonical Artifact

- `artifacts/proof/current/production_preflight.md`

## Required Production Controls

The preflight checks at least the following:

- production-like environment selected
- strong JWT secret configured
- legacy admin token path disabled
- Redis configured for rate limiting
- evidence store root configured, exists, writable, and outside repo by default
- CORS allowlist set and not wildcard
- egress proxy configured (or explicit non-prod override)
- database URL configured
- debug mode disabled
- backup policy configured

## Truth Policy

- Production ready: FALSE until preflight passes.
- No legal authority claims.
- No autonomous public publication claims.
- No claim that all sources are runnable.
