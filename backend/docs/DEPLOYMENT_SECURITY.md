# Deployment Security

**Date**: 2026-05-02  
**Status**: Research Alpha — Local Development Only

---

## ⚠️ Production Readiness Warning

> Judge Atlas is currently a **research alpha** hardened prototype.
> 
> **DO NOT deploy to public-facing production** without completing the hardening items below.

---

## Rate Limiting

### Current Implementation

- **Library**: slowapi (in-memory)
- **Status**: LOCAL-ONLY / SINGLE-PROCESS

### Limitations

- ❌ Does not scale across multiple workers/processes
- ❌ Rate limit counters reset on server restart
- ❌ Not suitable for multi-instance deployments
- ❌ Shared memory only, no distributed state

### Production Requirements

- [ ] Redis-backed rate limiting
- [ ] Consistent state across all workers
- [ ] Per-endpoint rate limit configuration
- [ ] Different limits for public vs admin endpoints

### Recommended Configuration

```python
# Development (current)
Redis rate limiting: Not required

# Production
Redis rate limiting: Required
  - public endpoints: 100 req/min per IP
  - admin endpoints: 30 req/min per user
  - ingestion endpoints: 10 req/min per source
```

---

## Proxy Trust

### X-Forwarded-For Handling

**Current behavior**: `X-Forwarded-For` is trusted **only** when the direct
connection IP (`request.client.host`) exactly matches one of the IPs listed
in `JTA_TRUSTED_PROXY_IPS` (comma-separated exact IPv4/IPv6 addresses).
If the connection is not from a trusted proxy IP, the direct client host is
used and `X-Forwarded-For` is ignored entirely.

> ⚠️ CIDR ranges are **not** supported — only exact IP addresses.
> Configure your reverse proxy's egress IP(s) in `JTA_TRUSTED_PROXY_IPS`.

### When This is Safe

✅ Behind a trusted reverse proxy that:
- Sets `X-Forwarded-For` correctly
- Strips client-spoofed values
- Blocks direct client access
- Has a stable, known egress IP listed in `JTA_TRUSTED_PROXY_IPS`

### When This is NOT Safe

❌ Direct client access allowed — clients can spoof `X-Forwarded-For` and bypass rate limits

### Required Configuration

```bash
# Production: list exact IP(s) of your reverse proxy
JTA_TRUSTED_PROXY_IPS=10.0.0.1,10.0.0.2
```

> Note: CIDR ranges such as `10.0.0.0/8` are not parsed — provide the exact
> IP address(es) your proxy will connect from.

---

## Database Security

### Current

- SQLite for local development
- PostgreSQL supported but not CI-tested

### Production Requirements

- [ ] PostgreSQL 14+ with SSL/TLS
- [ ] PostGIS 3.1+ for spatial data
- [ ] Connection pooling (PgBouncer)
- [ ] Database credentials in vault (not env vars)
- [ ] Row-level security policies
- [ ] Encrypted at rest (AWS RDS, Azure Database)

---

## Secrets Management

### Current

- `.env` files with plain text values
- `JTA_ADMIN_REVIEW_TOKEN` in environment

### Production Requirements

- [ ] HashiCorp Vault or cloud-native secrets manager
- [ ] Automatic secret rotation
- [ ] No secrets in environment variables
- [ ] No secrets in code or containers
- [ ] Runtime secret injection

---

## Network Security

### Current

- Basic FastAPI CORS
- No security headers configured

### Production Requirements

- [ ] Security headers middleware:
  - Strict-Transport-Security (HSTS)
  - Content-Security-Policy
  - X-Content-Type-Options
  - X-Frame-Options
  - Referrer-Policy
- [ ] CORS restricted to known origins
- [ ] TLS 1.2+ only (no TLS 1.0/1.1)
- [ ] Certificate pinning (optional)

---

## Container Security

### Current

- Dockerfile with node:22-bookworm-slim and python:3.11-slim
- Non-root user in frontend container

### Production Requirements

- [ ] Distroless or minimal base images
- [ ] No build tools in production images
- [ ] Image scanning (Trivy, Snyk)
- [ ] Signed container images
- [ ] Read-only filesystem
- [ ] Resource limits (CPU/memory)

---

## Monitoring & Alerting

### Production Requirements

- [ ] Structured logging (JSON)
- [ ] Centralized log aggregation
- [ ] Error tracking (Sentry)
- [ ] Security event alerting:
  - Failed auth attempts
  - Rate limit exceeded
  - Admin actions
  - Unusual access patterns
- [ ] Health checks and uptime monitoring

---

## Backup & Recovery

### Production Requirements

- [ ] Automated database backups
- [ ] Point-in-time recovery
- [ ] Backup encryption
- [ ] Regular recovery testing
- [ ] Source snapshot archival

---

## Compliance Considerations

### Legal/Privacy

- [ ] GDPR compliance (EU users)
- [ ] CCPA compliance (California users)
- [ ] Data retention policies
- [ ] Right to deletion
- [ ] Data processing agreements

### Audit

- [ ] Immutable audit logs
- [ ] Admin action history
- [ ] Source provenance tracking

---

## Security Checklist for Production

- [ ] Redis-backed rate limiting configured
- [ ] Trusted proxy configuration validated
- [ ] PostgreSQL SSL enforced
- [ ] Secrets in vault (not env vars)
- [ ] Security headers enabled
- [ ] CORS restricted
- [ ] Container images scanned
- [ ] Non-root containers
- [ ] Logging and monitoring active
- [ ] Automated backups configured
- [ ] Auth migrated from shared token
- [ ] RBAC implemented
- [ ] Audit logging enabled
- [ ] Security audit completed
- [ ] Penetration testing passed

---

## Immediate Actions Required

Before any production deployment:

1. **Replace shared token auth** with real user accounts (see AUTH_ROADMAP.md)
2. **Add Redis** for rate limiting
3. **Configure trusted proxy** settings
4. **Move secrets** to vault
5. **Enable security headers**
6. **Set up monitoring** and alerting
7. **Configure SSL/TLS** for PostgreSQL
8. **Scan container images**

---

## Security Contacts

- Security issues: [Report via GitHub Security Advisories]
- Emergency contact: [Configure before production]

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)
