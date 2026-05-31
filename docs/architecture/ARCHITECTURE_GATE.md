# Architecture Quality Gate

This document describes the quality gate requirements and how to run them.

## Purpose

The architecture gate ensures code quality, security, and structural integrity before deployment. It runs:

1. **Sentrux** - Static analysis for architecture rules
2. **Backend** - Compile checks and test suite
3. **Frontend** - Lint, type check, and build

## Prerequisites

- Python 3.11+ with backend virtual environment activated
- Node.js 20+ with frontend dependencies installed
- `sentrux` CLI tool (optional but recommended)

## Quick Start

```bash
# Run full quality gate
./scripts/quality_gate.sh

# Skip sentrux if not installed
ALLOW_MISSING_SENTRUX=1 ./scripts/quality_gate.sh
```

## Manual Steps

If you prefer to run checks individually:

### 1. Sentrux (Static Analysis)

```bash
# Check if sentrux is available
which sentrux || echo "sentrux not installed"

# Run sentrux checks
sentrux check .
```

If sentrux is not installed, the quality gate will fail unless `ALLOW_MISSING_SENTRUX=1` is set.

### 2. Backend Checks

```bash
cd backend
source .venv/bin/activate

# Compile check (syntax validation)
python -m compileall app/

# Run full test suite
python -m pytest -q
```

Expected: See CI or run `./scripts/verify_backend.sh` for current test count

### 3. Frontend Checks

```bash
cd frontend

# Install dependencies if needed
npm install

# Lint
npm run lint

# Type check
npm run typecheck  # or: npx tsc --noEmit

# Build
npm run build
```

Expected: No errors, build succeeds

## CI/CD Integration

The quality gate should run in CI before any deployment:

```yaml
# Example GitHub Actions step
- name: Quality Gate
  run: |
    cd scripts
    ./quality_gate.sh
  env:
    ALLOW_MISSING_SENTRUX: 1  # Optional: allow CI without sentrux
```

## Troubleshooting

### "sentrux: command not found"

Either:
1. Install sentrux: `pip install sentrux` (or see sentrux documentation)
2. Run with `ALLOW_MISSING_SENTRUX=1` to skip sentrux checks

### Backend tests fail

Check:
- Virtual environment activated
- Dependencies installed: `pip install -e ".[test]"`
- Database migrations up to date: `alembic upgrade head`

### Frontend build fails

Check:
- Node.js 20+ installed: `node --version`
- Dependencies installed: `npm install`
- No TypeScript errors: `npx tsc --noEmit`

## Rule Configuration

Sentrux rules are defined in `.sentrux/rules.toml`:

- `no_hardcoded_secrets` - Prevents API keys in code
- `no_import_cycles` - Enforces proper module structure
- `no_wildcard_cors` - Blocks wildcard CORS origins
- `require_https_in_prod` - Enforces HTTPS in production

## Exceptions

To add a temporary exception:

1. Document the exception in code comments
2. Add to `.sentrux/rules.toml` `[ignore]` section if permanent
3. Create a ticket to remove the exception

## References

- [Sentrux Documentation](https://github.com/sentrux/sentrux)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Next.js Linting](https://nextjs.org/docs/app/building-your-application/configuring/eslint)
