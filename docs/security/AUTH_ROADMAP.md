# Authentication Roadmap

## Current Status: Alpha (Shared-Token Auth Only)

The current authentication system uses a shared admin token for all admin operations. This is **acceptable for local development and private demos**, but **not suitable for public deployment**.

### Current Implementation
- **Single shared token** (`JTA_ADMIN_TOKEN`, `JTA_ADMIN_REVIEW_TOKEN`)
- **No per-user identity** — all valid tokens get the same admin privileges
- **No token revocation** — invalidating a token requires code changes and redeployment
- **No MFA** — two-factor authentication not supported
- **No audit trail of per-user actions** — all mutations logged as "shared-admin-token"
- **No session management** — tokens never expire

### Why This Matters
This architecture is intentional for alpha stability:
- Simplifies deployment and development
- Avoids dependency on external auth services
- Allows rapid iteration on core features

However, it creates accountability gaps:
- Multiple team members using the same token cannot be distinguished in audit logs
- A compromised token cannot be revoked without redeploy
- No way to restrict specific users to specific operations (e.g., reviewer vs. admin)

### Next Steps: Real Authentication (Phase 2)

Replace shared-token auth with one of these options:

#### Option 1: Clerk (Recommended)
- **Pros**: Zero-friction login, built-in MFA, per-user API keys
- **Integration**: Add Clerk middleware, extract user ID from JWT in audit logs
- **Cost**: Free tier up to 10,000 monthly active users
- **Docs**: https://clerk.com/docs

#### Option 2: Auth0
- **Pros**: Enterprise-grade, multi-tenant, extensive integrations
- **Integration**: OAuth 2.0 / OIDC, verify JWT, extract subject claim
- **Cost**: Free tier up to 10,000 users
- **Docs**: https://auth0.com/docs

#### Option 3: Supabase Auth
- **Pros**: Open-source alternative, PostgreSQL-native, self-hostable
- **Integration**: Use Supabase REST API, verify JWT with Supabase key
- **Cost**: Free tier included with Supabase database
- **Docs**: https://supabase.com/docs/guides/auth

#### Option 4: Local Users Table
- **Pros**: Full control, no external dependencies
- **Cons**: Responsibility for password security, MFA implementation
- **Integration**: SQLAlchemy models for users/roles, implement JWT token issuance
- **Cost**: None (but higher operational burden)

### Deprecation Plan

1. **Phase 1 (Current)**: Shared-token auth with clear documentation of limitations
2. **Phase 2 (Q3 2026)**: Add real auth option alongside shared-token (no breaking changes)
3. **Phase 3 (Q4 2026)**: Default to real auth, keep shared-token as development-only option
4. **Phase 4 (2027)**: Remove shared-token auth entirely

---

## Specific Gaps for External Audit (JUDGE-main 22)

The following gaps were identified in the external audit of JUDGE-main 22.  
These are documented here to establish a precise upgrade checklist for Phase 2.

### Identity & Attribution Gaps

| Gap | Current Behaviour | Fix in Phase 2 |
|-----|------------------|----------------|
| No per-user identity | `actor_id = "shared-admin-token"` for all callers | Extract OIDC `sub` claim as `actor_id`; store as user UUID |
| No role-based access control | Role is enforced by endpoint, not by credential | Issue scoped tokens: `source-admin`, `review-admin`, `system-admin` |
| Audit log non-attributable | Multiple operators indistinguishable in `audit_logs` | Each token maps to a user row; `actor_id` is the user UUID |
| No separate reviewer vs. importer identity | Single `JTA_ADMIN_TOKEN` covers both | `reviewer` and `importer` roles issued as separate OIDC scopes |

### Session & Token Lifecycle Gaps

| Gap | Current Behaviour | Fix in Phase 2 |
|-----|------------------|----------------|
| Tokens never expire | Leaked token valid until redeploy | OIDC short-lived access tokens + refresh tokens |
| No revocation | Revocation requires environment variable change + redeploy | OIDC token revocation endpoint; DB-level session invalidation |
| No MFA / second factor | Not supported | OIDC provider handles MFA transparently |
| No token rotation | Same static secret forever | OIDC providers rotate signing keys; tokens are time-bounded |

### Operational Gaps

| Gap | Current Behaviour | Fix in Phase 2 |
|-----|------------------|----------------|
| Shared secret in env var | `JTA_ADMIN_TOKEN` in `.env` / K8s secret | OIDC: secret is the provider's client_secret, never the user credential |
| No session management | Request is stateless token check only | OIDC session with configurable expiry |
| No concurrent session visibility | Cannot see who is logged in | OIDC provider surfaces active sessions; DB can record last-seen |

### Code locations that change in Phase 2

- `backend/app/auth/admin.py` — replace `_compare_token()` with JWT verification; update `require_admin_token()` to extract `sub` and `scope` claims
- `backend/app/auth/actor.py` — add `user_id: str | None` field to `AdminActor`
- `backend/app/models/entities.py` — add `User` model with id, email, roles, last_seen
- `backend/app/core/config.py` — add `JTA_OIDC_ISSUER`, `JTA_OIDC_CLIENT_ID`, `JTA_OIDC_CLIENT_SECRET` settings

### Implementation Checklist

When ready to implement real auth:
- [ ] Choose auth provider (Clerk, Auth0, Supabase, or local)
- [ ] Implement login UI in frontend
- [ ] Add JWT verification middleware to backend
- [ ] Update `AdminActor` to extract real user ID from JWT
- [ ] Update audit logging to use real user IDs (not "shared-admin-token")
- [ ] Add per-user role assignments (viewer, reviewer, source_admin, system_admin)
- [ ] Add token management endpoints (list, revoke)
- [ ] Add MFA setup flows
- [ ] Update documentation
- [ ] Migrate existing admin tokens to new system
- [ ] Deprecate shared-token auth in production

### Security Review Checklist (Before Public Launch)

- [ ] Replace shared-token auth with real authentication
- [ ] Enable HTTPS in production (not http://)
- [ ] Use strong API keys for CourtListener, external APIs
- [ ] Run security audit on database schema (no PII exposed without consent)
- [ ] Implement rate limiting with Redis backend (do not fail open in production)
- [ ] Add CORS allowlist validation (do not allow all origins)
- [ ] Review all public endpoints for information leakage
- [ ] Implement data retention policies for sensitive content
- [ ] Add backup/disaster recovery procedures
- [ ] Set up security event logging and alerting

---

**Do not proceed to public launch until real authentication is in place.**
