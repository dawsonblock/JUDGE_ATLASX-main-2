# Adding a New Source

This guide walks through adding a data source to the JUDGE source registry.

---

## Step 1 — Define the source in YAML

Add an entry to the appropriate YAML file under
`backend/app/ingestion/sources/`.  For a Saskatoon / Saskatchewan source,
edit `canada_saskatchewan_sources.yaml`.

```yaml
- source_key: my_new_source          # unique slug, snake_case
  name: "My New Source"
  source_type: official_open_data    # see canada-first-policy.md
  jurisdiction: CA-SK
  category: crime_statistics         # logical grouping
  priority: 3                        # lower = higher priority
  enabled_default: false             # ALWAYS false for new sources
  public_record_authority: official_open_data
  base_url: "https://opendata.example.ca"
  allowed_domains: '["opendata.example.ca"]'
  refresh_interval_minutes: 1440
  parser: ckan_api                   # see parser-keys.md
  creates: '["CrimeIncident"]'
  public_publish_default: false      # ALWAYS false for new sources
  auto_publish_enabled: false        # ALWAYS false for new sources
  requires_manual_review: true       # ALWAYS true for new sources
  terms_url: "https://opendata.example.ca/terms"
  admin_notes: "Added YYYY-MM-DD. Awaiting legal review."
```

> **Safety defaults**: `enabled_default`, `auto_publish_enabled`, and
> `public_publish_default` must all be `false`; `requires_manual_review` must
> be `true`.  The CI quality gate (`scripts/proof_sources.sh`) enforces this.

---

## Step 2 — Choose or create an adapter

If the source uses an existing data format, pick the matching `parser` key
from [parser-keys.md](parser-keys.md).

If no existing adapter fits, create a new one:

```
backend/app/ingestion/source_adapters/my_adapter.py
```

The adapter must extend `SourceAdapter`:

```python
from app.ingestion.adapters import SourceAdapter, IngestionResult, ParsedRecord

class MyAdapter(SourceAdapter):
    def fetch(self) -> list[dict]:
        ...

    def parse(self, raw: list[dict]) -> list[ParsedRecord]:
        ...

    def run(self) -> IngestionResult:
        from app.ingestion.source_rules import enforce_all, RuleViolation
        rows = self.fetch()
        parsed = self.parse(rows)
        created_records = []
        errors = []
        for record in parsed:
            violations = enforce_all(
                url=record.source_url or self.base_url,
                allowed_domains_json=self.allowed_domains_json,
                record_type="CrimeIncident",
                public_record_authority=self.public_record_authority,
                creates_json='["CrimeIncident"]',
                auto_publish_enabled=False,
                public_publish_default=False,
            )
            if violations:
                errors.append(str(violations[0]))
                continue
            # ... write to DB ...
        return IngestionResult(
            source_key=self.source_key,
            records_fetched=len(rows),
            records_skipped=len(rows) - len(created_records),
            created_records=created_records,
            review_items=[],
            errors=errors,
        )
```

Then register it in `source_adapters/__init__.py`:

```python
from .my_adapter import MyAdapter

ADAPTER_REGISTRY = {
    ...
    "my_parser_key": MyAdapter,
}
```

---

## Step 3 — Write tests

Add tests to `backend/app/tests/`:

- Verify YAML safety defaults are preserved.
- Verify `fetch()` returns `[]` on domain violation.
- Verify `parse([])` returns `[]`.
- If the adapter calls an external API, mock it with `pytest-httpx` or
  `responses`.

---

## Step 4 — Run the proof script

```bash
bash scripts/proof_sources.sh
```

This checks that all sources in YAML have the required safety defaults and
that every `parser` key resolves in `ADAPTER_REGISTRY`.

---

## Step 5 — Update docs

Add your source to the table in [overview.md](overview.md) and note the
authority tier in [canada-first-policy.md](canada-first-policy.md) if it
introduces a new tier.
