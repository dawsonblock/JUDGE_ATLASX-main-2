# Canada-First Source Policy

JUDGE is a Canadian judicial-accountability tracker.  The source registry
prioritises **official Canadian government and court data** before any
commercial or news sources.

---

## Jurisdiction priority

1. **Saskatchewan** – Saskatoon Open Data Portal, SK Courts, SK Legislature, SK Statistics
2. **Federal Canada** – Statistics Canada, CanLII, Federal Court, SCC (Lexum), Laws.justice.gc.ca
3. **Pan-Canadian open data** – Federal CKAN portal (`open.canada.ca`)
4. **News / context only** – RSS/web sources; never create structured records

---

## Authority tiers

| Tier | `public_record_authority` | May create | Auto-publish eligible |
|------|--------------------------|------------|-----------------------|
| Official open data | `official_open_data` | `CrimeIncident`, `ReviewItem` | ✅ (with flags) |
| Official statistics | `official_statistics` | `CrimeIncident`, `ReviewItem` | ✅ (with flags) |
| Official government | `official_government` | `CrimeIncident`, `ReviewItem` | ✅ (with flags) |
| Court record | `official_court_record` | `ReviewItem` only | ❌ always manual |
| Legislation | `official_legislation` | `ReviewItem` only | ❌ always manual |
| News / context | `news_context` | `ReviewItem` only | ❌ always manual |
| Unknown | `unknown` | ❌ nothing | ❌ always manual |

---

## Default safety posture

Every source in `canada_saskatchewan_sources.yaml` ships with:

```yaml
enabled_default: false         # operator must explicitly activate
auto_publish_enabled: false    # never auto-publish without review
requires_manual_review: true   # all records pass through review queue
public_publish_default: false  # records start private
```

An operator may relax these only after verifying the source feed and
consulting the terms of use (`terms_url`).

---

## Rationale

- Court and legislation records contain personally identifying information and
  must never be published without legal review.
- News sources provide *context* for investigators, not structured facts that
  could imply guilt.
- Statistics sources produce aggregate data that is low-risk but should still
  be verified before publication to prevent mis-attribution.
