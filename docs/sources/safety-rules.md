# Safety Rules

`backend/app/ingestion/source_rules.py` is the single enforcement point for
all ingestion safety constraints.  No adapter may bypass these rules.

---

## Rules

### 1  Domain allow-list (`check_domain_allowed`)

Before any HTTP request, the adapter's target URL is checked against the
`allowed_domains` JSON list on the source.

- If `allowed_domains` is `null`, empty, malformed, or missing, fetch is **blocked**. Only explicitly listed domains are allowed.
- If `allowed_domains` is a non-empty list, the URL's hostname must be in that list.
- Malformed JSON or an unparseable URL → **blocked** (fail-closed).

### 2  Record-type gate (`check_record_type_allowed`)

The record type that an adapter intends to create (`CrimeIncident` or
`ReviewItem`) must be:

1. Listed in the source's `creates` JSON array.
2. Permitted by the source's `public_record_authority` tier.

Authority → permitted record types:

| Authority | CrimeIncident | ReviewItem |
|-----------|:---:|:---:|
| `official_open_data` | ✅ | ✅ |
| `official_statistics` | ✅ | ✅ |
| `official_government` | ✅ | ✅ |
| `official_court_record` | ❌ | ✅ |
| `official_legislation` | ❌ | ✅ |
| `news_context` | ❌ | ✅ |
| `unknown` | ❌ | ❌ |

### 3  Publish gate (`check_publish_gate`)

Auto-publishing is only permitted when **all three** conditions are met:

1. `public_record_authority` is in `{official_open_data, official_statistics, official_legislation, official_government}`.
2. `auto_publish_enabled=True` on the source row.
3. `public_publish_default=True` on the source row.

If any condition fails, the record is routed to the review queue.

---

## `enforce_all`

The convenience function `enforce_all(...)` runs all three checks and returns
every `RuleViolation` found (empty list = safe to proceed).

```python
violations = enforce_all(
    url=target_url,
    allowed_domains_json=source.allowed_domains,
    record_type="CrimeIncident",
    public_record_authority=source.public_record_authority,
    creates_json=source.creates,
    auto_publish_enabled=source.auto_publish_enabled,
    public_publish_default=source.public_publish_default,
)
if violations:
    # route to review queue or abort
```

---

## Fail-closed design

- Unknown authority → all record types blocked.
- JSON parse error on `allowed_domains` or `creates` → violation raised.
- Any single violation on `enforce_all` → caller must **not** write the record
  to the public table.
