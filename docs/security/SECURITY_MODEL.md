# Security Model

Canonical security model for alpha runtime.

## Core Controls

- JWT + RBAC required for mutation endpoints
- legacy shared-token mutation paths must remain disabled
- startup blockers fail closed for unsafe production settings
- mutation actions must be audited with actor and before/after state

## Production Startup Blockers

Startup must fail when any of the following are true:

- weak placeholder JWT secret
- JWT auth disabled
- legacy shared-token admin auth enabled
- Redis rate limiting unavailable in production mode
- evidence store requirement disabled
- review gating disabled
- audit chain protections disabled
- wildcard CORS in production
- non-HTTPS production origins

## Boundary Safety

Runtime must not import from archived/reference paths.
