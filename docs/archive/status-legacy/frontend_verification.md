# Frontend Verification

## Node Version Requirement

The frontend requires **Node 20.x**.  `frontend/package.json` specifies
`engines: {"node": "20.x"}` and `frontend/.npmrc` sets `engine-strict=true`,
which causes `npm ci` to fail if a non-matching Node version is active.

## Local Setup

```bash
nvm install 20    # skip if Node 20 is already installed
nvm use 20        # activate Node 20 for this shell session
node --version    # should print v20.x.x
```

## Manual Verification Steps

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test:contracts
npm run build
```

## Common Failure: Wrong Node Version on PATH

If you see `npm warn EBADENGINE` or a Node engine error, your shell is using a
different Node (often the system default — e.g. Node 24.x from a Homebrew or
system install).

Always run `nvm use 20` **before** any frontend work in this repository.

To auto-switch when entering the project directory, add to `~/.zshrc`:

```bash
autoload -U add-zsh-hook
load-nvmrc() {
  local nvmrc_path
  nvmrc_path="$(nvm_find_nvmrc)"
  if [ -n "$nvmrc_path" ]; then
    nvm use
  fi
}
add-zsh-hook chpwd load-nvmrc
load-nvmrc
```

## CI

GitHub Actions (`quality-gate.yml`) pins `node-version: "20"` via `actions/setup-node@v4`.

Local `release_gate.py` sources nvm and runs `nvm use 20` before each npm step,
emitting `BLOCKED_NODE_VERSION` and returning exit 1 if Node 20 is not installed
under nvm.

## Reference

- `.nvmrc` — specifies `20`
- `frontend/package.json` — `engines: {"node": "20.x"}`
- `frontend/.npmrc` — `engine-strict=true`
- `frontend/Dockerfile` — `FROM node:20-slim`

