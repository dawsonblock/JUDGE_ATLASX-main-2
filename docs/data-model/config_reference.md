<!-- markdownlint-disable -->

# JudgeTracker Atlas — Configuration Reference

All environment variables use the `JTA_` prefix and can be set via `.env`,
docker-compose environment block, or the host shell.

For a copy-and-edit production template see `backend/.env.production.example`.

---

## Core

| Variable           | Type   | Default                       | Description                                                                                                                   |
| ------------------ | ------ | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `JTA_APP_ENV`      | string | `development`                 | Runtime environment. Accepted: `development`, `staging`, `production`. Production mode activates all hard-fail safety checks. |
| `JTA_DATABASE_URL` | string | `sqlite:///./judgetracker.db` | SQLAlchemy connection string. Use PostgreSQL in production with `postgresql+psycopg://` (psycopg v3 dialect).               |
| `JTA_APP_NAME`     | string | `JudgeTracker Atlas`          | Application display name.                                                                                                     |

---

## Security

| Variable                              | Type   | Default                       | Description                                                                                                                                                                              |
| ------------------------------------- | ------ | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `JTA_JWT_SECRET_KEY`                  | string | `CHANGE-ME-BEFORE-PRODUCTION` | HMAC key for signing JWT access and refresh tokens. **Required in production.** Must be ≥ 32 random characters. Generate: `python -c 'import secrets; print(secrets.token_urlsafe(48))'` |
| `JTA_JWT_ALGORITHM`                   | string | `HS256`                       | JWT signing algorithm.                                                                                                                                                                   |
| `JTA_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | int    | `30`                          | Access token lifetime.                                                                                                                                                                   |
| `JTA_JWT_REFRESH_TOKEN_EXPIRE_DAYS`   | int    | `7`                           | Refresh token lifetime.                                                                                                                                                                  |
| `JTA_JWT_AUTH_ENABLED`                | bool   | `false`                       | Must be `true` in production. Set to `true` after creating the first admin account. **Startup fails in production if this is false.**                                                    |
| `JTA_FIRST_ADMIN_SECRET`              | string | `null`                        | Bootstrap secret for the first admin registration endpoint. Rejected at startup if it looks like a placeholder.                                                                          |
| `JTA_ENABLE_LEGACY_ADMIN_TOKEN`       | bool   | `false`                       | Deprecated shared-token admin auth. **Must remain false in production; startup errors if true.**                                                                                         |
| `JTA_ADMIN_TOKEN`                     | string | `null`                        | Deprecated legacy admin token. Unset in production.                                                                                                                                      |
| `JTA_ADMIN_REVIEW_TOKEN`              | string | `null`                        | Deprecated legacy admin review token. Unset in production.                                                                                                                               |
| `JTA_ENFORCE_JWT_MUTATIONS`           | bool   | `true`                        | When true, shared-token actors are rejected for mutation operations.                                                                                                                     |

---

## CORS

| Variable           | Type         | Default                  | Description                                                                                          |
| ------------------ | ------------ | ------------------------ | ---------------------------------------------------------------------------------------------------- |
| `JTA_CORS_ORIGINS` | string (CSV) | `https://localhost:3000` | Comma-separated list of allowed origins. Wildcards and non-HTTPS origins are rejected in production. |

---

## Rate Limiting

| Variable                   | Type         | Default  | Description                                                                                 |
| -------------------------- | ------------ | -------- | ------------------------------------------------------------------------------------------- |
| `JTA_RATE_LIMIT_ENABLED`   | bool         | `true`   | Master switch for all rate limiting.                                                        |
| `JTA_RATE_LIMIT_BACKEND`   | string       | `memory` | Storage backend. `memory` (single-node only) or `redis`. **Production should use `redis`.** |
| `JTA_REDIS_URL`            | string       | `null`   | Redis connection URL. Required when `JTA_RATE_LIMIT_BACKEND=redis`.                         |
| `JTA_RATE_LIMIT_PUBLIC`    | int          | `100`    | Requests per minute for public API endpoints.                                               |
| `JTA_RATE_LIMIT_ADMIN`     | int          | `30`     | Requests per minute for admin API endpoints.                                                |
| `JTA_RATE_LIMIT_MAP`       | int          | `60`     | Requests per minute for map endpoints.                                                      |
| `JTA_RATE_LIMIT_INGESTION` | int          | `10`     | Requests per minute for ingestion trigger endpoints.                                        |
| `JTA_TRUSTED_PROXY_IPS`    | string (CSV) | `""`     | Comma-separated proxy IPs whose `X-Forwarded-For` header is trusted.                        |

> **Production note**: `JTA_RATE_LIMIT_BACKEND=memory` is rejected at startup in production unless `JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION=1` is set to acknowledge the single-node constraint.

---

## Evidence Store

| Variable                         | Type   | Default | Description                                                                    |
| -------------------------------- | ------ | ------- | ------------------------------------------------------------------------------ |
| `JTA_EVIDENCE_STORE_ROOT`        | string | `null`  | Absolute path to the evidence vault directory.                                 |
| `JTA_EVIDENCE_STORE_REQUIRED`    | bool   | `false` | When true (required in production), startup fails if the store is unreachable. |
| `JTA_EVIDENCE_STORE_PROBE_WRITE` | bool   | `true`  | Probe write access to the store at startup.                                    |

---

## Egress / Outbound Fetches

| Variable                                          | Type   | Default | Description                                                                                                                |
| ------------------------------------------------- | ------ | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `JTA_FETCH_EGRESS_PROXY`                          | string | `null`  | HTTP/HTTPS proxy URL for all outbound ingestion fetches. **Required in production** to mitigate DNS rebinding attacks.     |
| `JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY` | string | `null`  | Set to `1` to acknowledge that egress is enforced at the infrastructure level and suppress the egress proxy startup check. |

---

## Source Registry & Ingestion

| Variable                   | Type | Default | Description                                                                    |
| -------------------------- | ---- | ------- | ------------------------------------------------------------------------------ |
| `JTA_SEED_SOURCE_REGISTRY` | bool | `true`  | Seed the source registry from YAML on startup. Safe in production; idempotent. |
| `JTA_AUTO_SEED`            | bool | `false` | Seed sample data on startup. Development only; never enable in production.     |
| `JTA_ENABLE_SCHEDULER`     | bool | `false` | Start the APScheduler background worker.                                       |

---

## External Data Sources

| Variable                      | Type   | Default                                     | Description                                                   |
| ----------------------------- | ------ | ------------------------------------------- | ------------------------------------------------------------- |
| `JTA_CANLII_API_KEY`          | string | `null`                                      | CanLII REST API v1 key (Canadian case law).                   |
| `JTA_COURTLISTENER_API_TOKEN` | string | `null`                                      | CourtListener API token (US federal courts).                  |
| `JTA_COURTLISTENER_BASE_URL`  | string | `https://www.courtlistener.com/api/rest/v4` | CourtListener API base URL.                                   |
| `JTA_GEONAMES_USERNAME`       | string | `null`                                      | GeoNames API username.                                        |
| `JTA_LEXUM_API_KEY`           | string | `null`                                      | Lexum SCC bulk API key for historical SCC decision back-fill. |

---

## Feature Flags

| Variable                                   | Type | Default | Description                                                                          |
| ------------------------------------------ | ---- | ------- | ------------------------------------------------------------------------------------ |
| `JTA_ENABLE_ADMIN_IMPORTS`                 | bool | `false` | Enable the admin import API.                                                         |
| `JTA_ENABLE_ADMIN_REVIEW`                  | bool | `false` | Enable the admin review API.                                                         |
| `JTA_ENABLE_PUBLIC_EVENT_POST`             | bool | `false` | Allow public event POST requests.                                                    |
| `JTA_ENABLE_PUBLIC_PLATFORM`               | bool | `false` | Enable donor public-platform surfaces. Keep disabled until hardening gates pass.     |
| `JTA_ENABLE_PUBLIC_RELATIONSHIP_ARCS`      | bool | `false` | Publish relationship arc edges publicly. Requires manual review and policy sign-off. |
| `JTA_PUBLIC_RELATIONSHIP_ARC_MIN_EVIDENCE` | int  | `2`     | Minimum evidence references required on a published arc edge.                        |
| `JTA_PUBLIC_RELATIONSHIP_ARC_MAX_RESULTS`  | int  | `250`   | Hard cap on public arc results per request.                                          |
| `JTA_STATSCAN_ENABLED`                     | bool | `false` | Enable Statistics Canada ingestion.                                                  |
| `JTA_GDELT_ENABLED`                        | bool | `false` | Enable GDELT ingestion.                                                              |
| `JTA_LOCAL_FEEDS_ENABLED`                  | bool | `false` | Enable local feed ingestion.                                                         |

---

## Request Limits

| Variable                  | Type | Default    | Description                             |
| ------------------------- | ---- | ---------- | --------------------------------------- |
| `JTA_MAX_REQUEST_SIZE`    | int  | `10485760` | Max request body size in bytes (10 MB). |
| `JTA_MAX_CSV_UPLOAD_SIZE` | int  | `52428800` | Max CSV upload size in bytes (50 MB).   |
| `JTA_MAX_CSV_ROWS`        | int  | `1000000`  | Hard cap on CSV ingestion row count.    |

---

## Startup Validation Summary

When `JTA_APP_ENV=production`, the following checks run at startup and cause
a non-zero exit on failure:

1. `JTA_JWT_SECRET_KEY` — must be ≥ 32 chars and not a placeholder string.
2. `JTA_JWT_AUTH_ENABLED` — must be `true`.
3. `JTA_ENABLE_LEGACY_ADMIN_TOKEN` — must be `false`; `JTA_ADMIN_TOKEN` and `JTA_ADMIN_REVIEW_TOKEN` must be unset.
4. `JTA_CORS_ORIGINS` — must be explicit HTTPS URLs (no wildcards).
5. `JTA_RATE_LIMIT_BACKEND=redis` — Redis must be reachable; `memory` backend rejected unless override is set.
6. `JTA_EVIDENCE_STORE_REQUIRED=true` — must be set; store must be readable/writable.
7. `JTA_FETCH_EGRESS_PROXY` — must be set, or infrastructure override acknowledged.
