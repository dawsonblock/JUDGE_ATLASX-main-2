# Alpha Deployment

This is the canonical alpha deployment reference.

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

## Preconditions

- runtime boundaries pass
- proof command passes
- release zip validates cleanly

## Alpha Runtime Contract

Use explicit alpha-safe defaults:

- JTA_APP_ENV=alpha
- JTA_RUNTIME_PROFILE=alpha_docker
- JTA_DATABASE_URL=postgresql+psycopg://...
- JTA_REDIS_URL=redis://...
- JTA_JWT_SECRET_KEY=replace_with_long_random_secret
- JTA_JWT_ALGORITHM=HS256
- JTA_CORS_ORIGINS=https://alpha.example.com
- JTA_EVIDENCE_STORE_ROOT=/app/evidence
- JTA_EVIDENCE_STORE_REQUIRED=true
- JTA_STORAGE_BACKEND=local (or object storage backend when configured)
- JTA_ENABLE_PUBLIC_PLATFORM=false
- JTA_ENABLE_EXPERIMENTAL_LIVE_MAP=false
- JTA_ENABLE_WORKFLOW_ADMIN=false
- JTA_ENABLE_LEGACY_ADMIN_TOKEN=false
- JTA_FETCH_EGRESS_PROXY=http://egress-proxy:8080
- JTA_RATE_LIMIT_BACKEND=redis
- JTA_INGESTION_QUEUE_BACKEND=postgres

Notes:

- Experimental features are not production-safe and must remain disabled for alpha operations.
- This deployment target is not production. Production readiness remains false.

## Commands

```bash
make proof
make build-clean-release
make validate-release-zip
```

## Output Artifacts

- `artifacts/current/PROOF_REPORT.md`
- `artifacts/current/PROOF_MANIFEST.json`
- `artifacts/current/RELEASE_MANIFEST.json`
- `JUDGE_ATLASX-alpha-clean.zip`
