#!/usr/bin/env bash
# proof_sources.sh — Verify source-registry safety invariants for all YAML-defined sources.
#
# Checks for every source in canada_saskatchewan_sources.yaml:
#   1. enabled_default is false
#   2. requires_manual_review is true
#   3. auto_publish_enabled is false
#   4. parser key appears in ADAPTER_REGISTRY
#
# Exits non-zero and prints every failure before exiting.
# Usage: bash scripts/proof_sources.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Python validator (canonical checks including dup-key detection) ───────────
echo "=== validate_workflows.py ==="
python3 "$REPO_ROOT/scripts/validate_workflows.py"
echo ""

YAML_FILE="$REPO_ROOT/backend/app/ingestion/sources/canada_saskatchewan_sources.yaml"
ADAPTER_INIT="$REPO_ROOT/backend/app/ingestion/source_adapters/__init__.py"

echo "=== proof_sources.sh ==="
echo "YAML  : $YAML_FILE"
echo "Registry: $ADAPTER_INIT"
echo ""

FAILURES=0

# ── Helper: extract a field value for a source block ─────────────────────────
# We use awk to process the YAML linearly; this avoids a Python dependency for the
# shell step (Python is used for the adapter check below).

check_yaml_invariants() {
    local current_key=""
    local enabled_default=""
    local requires_manual_review=""
    local auto_publish_enabled=""
    local parser=""

    flush_source() {
        if [[ -z "$current_key" ]]; then return; fi

        local ok=1

        if [[ "$enabled_default" != "false" ]]; then
            echo "FAIL [$current_key] enabled_default must be false, got: '${enabled_default}'"
            FAILURES=$(( FAILURES + 1 ))
            ok=0
        fi

        if [[ "$requires_manual_review" != "true" ]]; then
            echo "FAIL [$current_key] requires_manual_review must be true, got: '${requires_manual_review}'"
            FAILURES=$(( FAILURES + 1 ))
            ok=0
        fi

        if [[ "$auto_publish_enabled" != "false" ]]; then
            echo "FAIL [$current_key] auto_publish_enabled must be false, got: '${auto_publish_enabled}'"
            FAILURES=$(( FAILURES + 1 ))
            ok=0
        fi

        if [[ -n "$parser" ]]; then
            check_adapter_key "$current_key" "$parser"
        else
            echo "FAIL [$current_key] parser key is missing"
            FAILURES=$(( FAILURES + 1 ))
            ok=0
        fi

        if [[ "$ok" == 1 ]]; then
            echo "OK    [$current_key] parser=$parser"
        fi
    }

    while IFS= read -r line; do
        # Strip leading whitespace for matching
        trimmed="${line#"${line%%[! ]*}"}"

        case "$trimmed" in
            "- source_key: "*)
                flush_source
                current_key="${trimmed#- source_key: }"
                # Reset per-source fields
                enabled_default=""
                requires_manual_review=""
                auto_publish_enabled=""
                parser=""
                ;;
            "enabled_default: "*)
                enabled_default="${trimmed#enabled_default: }"
                ;;
            "requires_manual_review: "*)
                requires_manual_review="${trimmed#requires_manual_review: }"
                ;;
            "auto_publish_enabled: "*)
                auto_publish_enabled="${trimmed#auto_publish_enabled: }"
                ;;
            "parser: "*)
                parser="${trimmed#parser: }"
                ;;
        esac
    done < "$YAML_FILE"

    flush_source
}

# ── Check adapter key appears in __init__.py ──────────────────────────────────
check_adapter_key() {
    local source_key="$1"
    local parser_key="$2"

    if grep -qF "\"${parser_key}\"" "$ADAPTER_INIT"; then
        return 0
    fi
    # Also try single-quote style
    if grep -qF "'${parser_key}'" "$ADAPTER_INIT"; then
        return 0
    fi
    echo "FAIL [$source_key] parser key '${parser_key}' not found in ADAPTER_REGISTRY"
    FAILURES=$(( FAILURES + 1 ))
}

# ── Run ───────────────────────────────────────────────────────────────────────
check_yaml_invariants

echo ""
if [[ "$FAILURES" -gt 0 ]]; then
    echo "RESULT: $FAILURES failure(s) found."
    exit 1
else
    echo "RESULT: All source safety invariants verified. ✓"
    exit 0
fi
