#!/usr/bin/env bash
# Guard: fail if any .pyc or __pycache__ files are committed to git,
# or exist on-disk when running outside a git repository.
set -euo pipefail

STRICT_ARCHIVE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --strict-archive)
            STRICT_ARCHIVE=true
            shift
            ;;
        *)
            echo "ERROR: unknown argument: $1"
            exit 2
            ;;
    esac
done

if [[ "${STRICT_ARCHIVE}" == "true" ]]; then
    # Strict release mode for extracted archives.
    if find . \
        \( -type d \( -name "__pycache__" -o -name ".pytest_cache" \) -print -quit \) \
        -o -type f \( -name "*.pyc" -o -name ".coverage" \) -print -quit | grep -q .; then
        echo "ERROR: Strict archive contamination check failed:"
        find . \
            \( -type d \( -name "__pycache__" -o -name ".pytest_cache" \) -print \) \
            -o -type f \( -name "*.pyc" -o -name ".coverage" \) -print | head -40
        exit 1
    fi
    echo "OK: Strict archive contamination check passed"
    exit 0
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git ls-files --cached | grep -qE '\.pyc$|__pycache__'; then
        echo "ERROR: Committed bytecode files detected:"
        git ls-files --cached | grep -E '\.pyc$|__pycache__'
        exit 1
    fi
else
    # Not in a git repo — fail on distributed cache/coverage artifacts.
    # Exclude dependency/build dirs where runtime tooling may write cache files.
    if find . \
        \( -type d \( -name ".venv" -o -name "node_modules" -o -name ".next" \) -prune \) \
        -o \( -type d -name "__pycache__" -o -type f \( -name "*.pyc" -o -name ".coverage" \) \) \
        -print -quit | grep -q .; then
        echo "ERROR: Generated cache/coverage files found on disk (non-git context):"
        find . \
            \( -type d \( -name ".venv" -o -name "node_modules" -o -name ".next" \) -prune \) \
            -o \( -type d -name "__pycache__" -o -type f \( -name "*.pyc" -o -name ".coverage" \) \) \
            -print | head -20
        exit 1
    fi
fi
echo "OK: No committed bytecode files"
