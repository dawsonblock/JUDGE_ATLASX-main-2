# Frontend Verification Guide

## Node Version Requirement

The frontend requires **Node 20**. This is enforced at three levels:

| Location | Setting |
|---|---|
| `frontend/.nvmrc` | `20` |
| `frontend/package.json` engines | `>=20.11.0` |
| `scripts/release_gate.py` | `nvm use 20` + `--expected-major 20` |
| `scripts/check_frontend_node_gate.py` | defaults `--expected-major 20` (accepts any 20.x; optional `--expected-minor` for exact 20.y.x) |

## Setup

```bash
# Install and activate Node 20 via nvm
nvm install 20
nvm use 20

# Verify
node --version   # must be v20.x.x

# Install dependencies
cd frontend
npm ci

# Run checks
npm run lint
npm run typecheck
npm run test:contracts
npm run build
```

## Automatic Version Switching

With `frontend/.nvmrc` present, `nvm` will automatically switch to Node 20 when you `cd frontend` if you have `nvm` shell hooks enabled.

## Common Failure Modes

### `BLOCKED_NODE_VERSION`
The release gate emits this signal when `nvm use 20` fails. Fix:
```bash
nvm install 20
nvm use 20
```

### `engine-strict` rejection
`frontend/.npmrc` sets `engine-strict=true`. If you run `npm install` or `npm ci`
under the wrong Node version, npm will reject with an engines violation. Fix:
switch to Node 20 first, then retry.

### `vitest: command not found`
Occurs when `npm ci` was not run. Run `npm ci` under Node 20 before running tests.

## CI Reference

The release gate (`scripts/release_gate.py`) runs all frontend steps under
`nvm use 20` and validates the version with `scripts/check_frontend_node_gate.py`.

A mismatch between the running Node version and Node 20 causes the
`frontend_node_gate` step to emit `BLOCKED_NODE_VERSION` and fail with exit 1.
The gate does not fall back to other Node versions.
