# Authentication Roadmap

**Date**: 2026-05-02  
**Status**: Local-Alpha (Shared Token Only)

---

## Current State

The prototype uses **shared-token authentication** for admin endpoints:

- Header: `X-JTA-Admin-Token`
- Token configured via: `JTA_ADMIN_REVIEW_TOKEN` environment variable
- Enabled via: `JTA_ENABLE_ADMIN_REVIEW=true`

**This is acceptable for local development only.**

---

## Why Shared Token is NOT Production-Safe

1. **No user identification** — All admins appear as the same entity
2. **No audit trail** — Cannot trace actions to individuals
3. **No rotation** — Single point of compromise
4. **No session expiry** — Token valid indefinitely
5. **No permission levels** — All-or-nothing access

---

## Required Future Work

### Phase 1: User Accounts
- [ ] User database table
- [ ] Password hashing (bcrypt/Argon2)
- [ ] Registration flow with email verification
- [ ] Login/logout endpoints
- [ ] Session management

### Phase 2: Roles & Permissions
- [ ] Role-based access control (RBAC)
- [ ] Roles: `viewer`, `reviewer`, `admin`, `superadmin`
- [ ] Permission matrix:
  - `viewer`: Read public data only
  - `reviewer`: View queue, make review decisions
  - `admin`: Full admin API access
  - `superadmin`: User management, system config

### Phase 3: Per-User Audit Logs
- [ ] `user_action_logs` table
- [ ] Log all review decisions with user ID
- [ ] Log admin API calls
- [ ] Immutable log storage
- [ ] Admin action history UI

### Phase 4: Token Security
- [ ] JWT with expiry (15-60 minutes)
- [ ] Refresh token rotation
- [ ] Secure cookie storage (HttpOnly, Secure, SameSite)
- [ ] Token revocation list for logout

### Phase 5: OAuth/OIDC Integration
- [ ] Support external identity providers:
  - Google Workspace
  - Microsoft Entra ID
  - GitHub
  - Generic OIDC
- [ ] SAML 2.0 for enterprise
- [ ] MFA/2FA support (TOTP, WebAuthn)

### Phase 6: Production Security Hardening
- [ ] Password complexity requirements
- [ ] Account lockout after failed attempts
- [ ] Rate limiting on auth endpoints
- [ ] CSRF protection
- [ ] Security headers (HSTS, CSP, etc.)
- [ ] Secrets management (HashiCorp Vault, AWS Secrets Manager)

---

## Recommended Implementation Path

### Immediate (Next 2-4 weeks)
1. Add `users` and `roles` tables
2. Implement basic login with hashed passwords
3. Replace shared token with JWT sessions
4. Add per-user audit logging

### Short-term (1-3 months)
1. Implement RBAC throughout admin API
2. Add user management UI
3. Session expiry and refresh
4. Production secrets validation

### Medium-term (3-6 months)
1. OAuth/OIDC integration
2. MFA support
3. Enterprise SAML
4. Security audit and penetration testing

---

## Current vs Future

| Feature | Current (Shared Token) | Future (Real Auth) |
|---------|------------------------|-------------------|
| User identity | ❌ None | ✅ Unique users |
| Audit trail | ⚠️ Partial | ✅ Per-user logs |
| Token rotation | ❌ Manual env var | ✅ Automatic refresh |
| Session expiry | ❌ Never | ✅ Configurable |
| Permission levels | ❌ All-or-nothing | ✅ Granular RBAC |
| OAuth/OIDC | ❌ None | ✅ Multiple providers |
| MFA | ❌ None | ✅ TOTP/WebAuthn |
| Password policies | ❌ N/A | ✅ Complexity rules |
| Account lockout | ❌ None | ✅ Brute-force protection |

---

## Acceptance Criteria for Production Auth

- [ ] Users can register and log in
- [ ] Passwords are properly hashed
- [ ] Sessions expire and can be refreshed
- [ ] Users have roles with granular permissions
- [ ] All admin actions are logged with user ID
- [ ] Audit logs are immutable
- [ ] Tokens can be revoked
- [ ] OAuth/OIDC providers work
- [ ] MFA is available
- [ ] Security audit passed

---

## Migration Path

When real auth is implemented:

1. Add new auth system alongside shared token
2. Create initial admin user accounts
3. Migrate existing review actions to system user
4. Deprecate shared token in production mode
5. Remove shared token after full migration

---

## Notes

- **Do NOT deploy shared token auth to public production**
- **Do use shared token for local development only**
- **Do prioritize user audit logging even before full OAuth**
- **Do consider compliance requirements (GDPR, CCPA, etc.)**
