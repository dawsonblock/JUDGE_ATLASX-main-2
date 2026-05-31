# Local Auth Bootstrap

This document defines the local development bootstrap for JWT-first admin auth.

## Default Security Posture

- `JTA_ENABLE_LEGACY_ADMIN_TOKEN=false`
- `JTA_ENFORCE_JWT_MUTATIONS=true`
- Shared-token auth is disabled by default.
- Mutation routes require JWT actors when JWT enforcement is enabled.

## Local JWT Bootstrap (Recommended)

1. Start services:

```bash
make dev
```

2. Ensure backend env uses JWT-first settings:

```bash
export JTA_JWT_AUTH_ENABLED=true
export JTA_ENABLE_LEGACY_ADMIN_TOKEN=false
export JTA_ENFORCE_JWT_MUTATIONS=true
```

3. Create first admin user (if needed):

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.test","password":"change-me-strong","role":"owner"}'
```

4. Login to obtain access token:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.test","password":"change-me-strong"}'
```

5. Use bearer token for admin APIs:

```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/api/admin/sources
```

## Legacy Shared-Token Mode (Local Compatibility Only)

Use only if JWT bootstrap is unavailable for local troubleshooting.

```bash
export JTA_ENABLE_LEGACY_ADMIN_TOKEN=true
export JTA_ENFORCE_JWT_MUTATIONS=false
export JTA_ADMIN_TOKEN=local-dev-token
```

Warnings:

- Never enable legacy shared-token mode in production.
- Shared tokens are deprecated and provide weaker identity attribution.

## Compose Guard Validation

Validate compose defaults remain JWT-first compatible:

```bash
backend/.venv/bin/python scripts/check_compose_auth_defaults.py --compose docker-compose.yml
```
