# SOURCE GOVERNANCE

## Required Source Controls
- Explicit source class and automation status.
- Explicit review/publication defaults.
- Declared legal/access basis and allowed domains where applicable.
- Declared creation targets (`creates`) and ingest cadence.

## Validation Path
Run:
- `python -m backend.tools.validate_sources`

Validation fails on:
- duplicate source keys,
- unknown source classes,
- missing publication/review policy fields,
- runnable status assigned to non-runnable class,
- machine-ingest contract violations,
- malformed list JSON fields.

## Operational Policy
- Contract failures are treated as governance violations.
- Violating sources must be corrected or disabled before normal ingestion resumes.
