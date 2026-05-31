# JUDGECTL Contract

This document defines the strict contract for AI agents operating THE-JUDGE platform via the `judgectl` CLI.

## Purpose
`judgectl` is the exclusive control surface for AI agents to interact with THE-JUDGE backend. Agents must never directly manipulate the database, bypass the ingestion queue, or execute uncontrolled web scraping.

## The JSON Envelope
All commands must be executed with the `--json` flag. The CLI guarantees a stable JSON envelope for all responses.

**Success Envelope:**
```json
{
  "ok": true,
  "command": "command.name",
  "data": { ... },
  "warnings": [],
  "errors": []
}
```

**Error Envelope:**
```json
{
  "ok": false,
  "command": "command.name",
  "error_code": "ERROR_CODE",
  "message": "Human readable message",
  "next_action": "Suggested next step for the agent"
}
```

## Source Management Rules
1. **List Sources:** Use `judgectl --json sources list` to view available sources.
2. **Source Info:** Use `judgectl --json sources info SOURCE_KEY` to check configuration.
3. **Runnable Sources:** Only sources with `source_class == "machine_ingest"` can be enabled or run.
4. **Mutations:** Commands that change state (e.g., `enable`, `disable`) require the `--yes` flag to confirm intent.

## Ingestion Rules
1. **Execution:** Agents trigger ingestion via `judgectl --json ingest run SOURCE_KEY`.
2. **Safety:** The backend enforces rate limits, domain allowlists, and record type restrictions.
3. **Provenance:** Every ingested record must have a corresponding raw evidence snapshot.

## Audit and Verification
Agents should regularly verify system health and configuration:
- `judgectl --json health`
- `judgectl --json audit guards`
- `judgectl --json sources validate`
