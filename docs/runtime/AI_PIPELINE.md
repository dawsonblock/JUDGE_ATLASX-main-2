# AI-Assisted Ingestion Pipeline

> **All classification is rule-based. No LLM calls are made unless `JTA_EMBEDDINGS_ENABLED=true`.**

JudgeTracker Atlas treats AI as an evidence clerk, not an authority. The v1 pipeline is deterministic and local: it uses rules to redact, classify, summarize, suggest links, and create review items. It does not call an external model provider.

The assistant layer is evidence-bound/citation-bound: memory and summaries are derivative and may not outrank reviewed source evidence.

Legal-context citations are allowed only for approved/public legal instruments and sections. Pending or rejected legal records must not be cited in public/evidence-chat responses.

## Rules

- AI outputs require schema validation before storage.
- AI-created records enter admin review as drafts.
- High-risk claims require human/admin review before any public display.
- News-only records cannot verify legal outcomes.
- Crime incidents are reported incidents, not proof of guilt or conviction.
- Private addresses, victim/suspect private data, DOBs, phone numbers, emails, family details, medical details, minor identities, and exact residential coordinates must be redacted or blocked.
- AI must not visually or legally link crime dots to judge decisions unless a court record, docket, police release, or other official outcome document supports the link.

## Pipeline

```text
raw source
-> privacy redaction
-> deterministic classification
-> neutral summary
-> entity-link suggestions
-> ReviewItem
-> admin approve/reject/block/publish decision
```

Publishing a legal-event draft creates a hidden `pending_review` event. It does not automatically create public accusations, repeat-offender conclusions, crime-to-case links, post-release outcome links, or news-only allegations.

## Web Monitoring Pipeline (Crawlee)

Crawlee integration for controlled source monitoring follows a separate pipeline:

```text
configured target (disabled by default)
-> admin enables target
-> Crawlee fetches (robots.txt intent; not runtime-configurable per-crawl, limits)
-> source snapshot saved (url, hash, timestamp, content)
-> narrow extractor creates candidate
-> ExtractedCandidate (confidence ≤ 0.5, warnings added)
-> source_verifier.py checks
-> public_safety.py screens for private data
-> publish_rules.py assigns review_required tier
-> pending_review queue
-> admin approve → public map
```

### Safety Controls

1. **Fail-closed** — Targets disabled by default, require explicit admin enable
2. **Strict allowlist** — Only configured domains (e.g., `saskatoonpolice.ca`)
3. **Hard limits** — max_requests (100), max_depth (3), concurrency (5)
4. **Evidence preservation** — Every fetch stored with hash for audit
5. **Never auto-publish** — All candidates → `pending_review` with low confidence
6. **Extractor validation** — Narrow extractors flag private patterns

### Crawlee vs Official APIs

| Source Type | Method | Trust Level |
|-------------|--------|-------------|
| CourtListener API | Official REST API | High |
| Police CSV import | Manual structured import | High |
| **Crawlee web monitor** | **Controlled page fetching** | **Medium-Low** |
| News/RSS feeds | Crawlee with extractors | Low |

Crawlee is for **source monitoring and evidence capture** — not as authoritative as official APIs. All crawled content requires human review.

## Admin Endpoints

All AI admin endpoints are disabled by default through `JTA_ENABLE_ADMIN_IMPORTS=false`.

- `GET /api/admin/review/items`
- `GET /api/admin/review/items/{id}`
- `POST /api/admin/review/items/{id}/approve`
- `POST /api/admin/review/items/{id}/reject`
- `POST /api/admin/review/items/{id}/needs-more-sources`
- `POST /api/admin/review/items/{id}/block`
- `POST /api/admin/review/items/{id}/publish`
- `POST /api/admin/ai/process-source/{source_id}`

This is a prototype control, not production auth or role management.

## Proof Commands

Run current-proof gates before making status claims:

- `backend/.venv/bin/python scripts/release_gate.py`
- `bash scripts/proof_all_current.sh`

Never present historical proof snapshots as current status.

