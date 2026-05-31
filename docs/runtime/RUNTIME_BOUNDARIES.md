# Runtime Boundaries

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

Canonical runtime boundary rules for alpha release.

## Allowed Runtime Surface

- `backend`
- `frontend`
- `docs`
- `deploy`
- `scripts`
- `tests`
- `artifacts/current`
- `tools`

## Explicitly Excluded From Runtime

- `external_reference`
- `artifacts/old`
- `artifacts/archive`
- `generated_logs`
- `tmp`
- `cache`
- old phase reports and duplicate status docs

## Enforcement

Validation command:

```bash
python3 scripts/validate_runtime_boundaries.py
```

This validator must pass in CI and proof execution.
