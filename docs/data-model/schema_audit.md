# Schema Audit — JudgeTracker Atlas (Historical Snapshot)

> ⚠️ HISTORICAL / SUPERSEDED DOCUMENT
> This schema audit was captured on 2026-05-01 and is not authoritative for current runtime truth.
> For current alpha proof status, use `artifacts/proof/current/CURRENT_PROOF.md` and
> `artifacts/proof/current/release_gate.json`.
> The authoritative runtime is `JUDGE-main/`; external folders are reference-only.

**Date (historical capture):** 2026-05-01  
**Canonical source at capture time:** `backend/app/models/entities.py` (SQLAlchemy ORM)  
**Status:** Historical schema audit notes; not a current release-proof assertion.

At capture time, ORM models were treated as authoritative for this audit pass.
Migration and drift statements below are historical notes and may not match current runtime state.

---

## Canonical Table List

| Table | ORM class |
|---|---|
| `locations` | `Location` |
| `courts` | `Court` |
| `judges` | `Judge` |
| `cases` | `Case` |
| `defendants` | `Defendant` |
| `case_parties` | `CaseParty` |
| `events` | `Event` |
| `event_defendants` | `EventDefendant` |
| `topics` | `Topic` |
| `event_topics` | `EventTopic` |
| `legal_sources` | `LegalSource` |
| `event_sources` | `EventSource` |
| `outcomes` | `Outcome` |
| `evidence_reviews` | `EvidenceReview` |
| `review_items` | `ReviewItem` |
| `review_action_logs` | `ReviewActionLog` |
| `crime_incidents` | `CrimeIncident` |
| `ingestion_runs` | `IngestionRun` |
| `audit_logs` | `AuditLog` |
| `crime_incident_sources` | `CrimeIncidentSource` |
| `crime_incident_event_links` | `CrimeIncidentEventLink` |
| `boundaries` | `Boundary` |
| `ai_correctness_checks` | `AICorrectnessCheck` |
| `ai_correctness_findings` | `AICorrectnessFinding` |
| `cl_bulk_provenance` | `CLBulkProvenance` |
| `court_listener_bulk_runs` | `CourtListenerBulkRun` |
| `source_snapshots` | `SourceSnapshot` |
| `source_registry` | `SourceRegistry` |
| `relationship_evidence` | `RelationshipEvidence` |
| `canonical_entities` | `CanonicalEntity` |
| `entity_source_records` | `EntitySourceRecord` |
| `entity_graph_edges` | `EntityGraphEdge` |
| `court_events` | `CourtEvent` |

---

## Per-Table Drift

### `locations`
**Status: MATCH** — no drift detected.

---

### `courts`
**Status: MATCH** — no drift detected.

---

### `judges`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `name` | `VARCHAR(120)` | `VARCHAR(255) NOT NULL` | Widen + NOT NULL |
| `normalized_name` | missing | `VARCHAR(255) NOT NULL UNIQUE INDEX` | Add |
| `title` | present | absent | Remove |
| `appointed_date` | present | absent | Remove |
| `biography` | present | absent | Remove |

---

### `cases`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `case_number` | present | absent | Remove |
| `caption` | `VARCHAR(255)` | `VARCHAR(500) NOT NULL` | Replace |
| `assigned_judge_id` | FK `judges.id` | absent | Remove |
| `date_filed` | present | `filed_date Date` | Rename |
| `status` | present | absent | Remove |
| `docket_number` | absent | `VARCHAR(120) NOT NULL` | Add |
| `normalized_docket_number` | absent | `VARCHAR(120) NOT NULL` | Add |
| `case_type` | absent | `VARCHAR(80) default 'criminal'` | Add |
| `terminated_date` | absent | `Date` | Add |
| `courtlistener_docket_id` | absent | `VARCHAR(80) INDEX` | Add |
| UniqueConstraint | absent | `(court_id, normalized_docket_number)` | Add |

---

### `defendants`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `anonymized_id` | `VARCHAR(32)` | `VARCHAR(24)` | Narrow |
| `date_of_birth` | present | absent | Remove |
| `normalized_public_name` | absent | `VARCHAR(255) INDEX` | Add |

---

### `case_defendants` → `case_parties`
**Status: TABLE REPLACED**

Migration creates `case_defendants(case_id, defendant_id)`.  
ORM uses `case_parties(case_id, defendant_id nullable, party_type NOT NULL, public_name, normalized_name, + timestamps)` with unique constraint `(case_id, normalized_name, party_type)`.  
**Fix:** Drop `case_defendants`, create `case_parties`.

---

### `events`
**Status: SIGNIFICANT DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `event_id` | `VARCHAR(80)` | `VARCHAR(64)` | Narrow |
| `event_date` | present | absent | Remove |
| `event_time` | present | absent | Remove |
| `description` | present (Text) | absent | Remove |
| `classification_summary` | present (Text) | absent | Remove |
| `classification_confidence` | present (Float) | absent | Remove |
| `classification_model` | present (VARCHAR(80)) | absent | Remove |
| `decision_date` | absent | `Date INDEX` | Add |
| `posted_date` | absent | `Date` | Add |
| `title` | absent | `VARCHAR(500) NOT NULL` | Add |
| `summary` | absent | `Text NOT NULL` | Add |
| `event_subtype` | absent | `VARCHAR(120)` | Add |
| `decision_result` | absent | `VARCHAR(120)` | Add |
| `source_quality` | absent | `VARCHAR(80) default 'court_record'` | Add |
| `classifier_metadata` | absent | `JSON` | Add |
| `repeat_offender_indicator` | `Boolean default False` | `repeat_offender_flag Boolean NOT NULL default False` | Rename column |
| `public_visibility` | `default True` | `NOT NULL default False INDEX` | Fix default + NOT NULL |
| `reviewed_at` | absent | `DateTime` | Add |
| `reviewed_by` | absent | `VARCHAR(120)` | Add |
| `review_notes` | absent | `Text` | Add |
| `correction_note` | absent | `Text` | Add |
| `dispute_note` | absent | `Text` | Add |
| `review_status` | `VARCHAR(40)` | `VARCHAR(80) NOT NULL INDEX` | Widen + NOT NULL |

---

### `event_defendants`
**Status: MATCH** — no drift detected.

---

### `topics`
**Status: MINOR DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `created_at` / `updated_at` | present | present (via TimestampMixin) | Match |

Matches.

---

### `event_topics`
**Status: MATCH** — no drift detected.

---

### `legal_sources`
**Status: SIGNIFICANT DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `source_name` | `VARCHAR(80)` | absent | Remove |
| `source_id` | `VARCHAR(255)` | `VARCHAR(64) NOT NULL UNIQUE INDEX` | Replace |
| `source_url` | `VARCHAR(500)` | `url Text NOT NULL` | Rename + widen |
| `source_api_url` | `VARCHAR(500)` | `api_url Text` | Rename |
| `source_public_url` | `VARCHAR(500)` | absent | Remove |
| `date_published` | `Date` | absent | Remove |
| `date_accessed` | `DateTime` | `retrieved_at DateTime` | Rename |
| `content_text` | `Text` | absent | Remove |
| `content_excerpt` | `Text` | absent | Remove |
| `source_metadata` | `JSON` | absent | Remove |
| `needs_correction_flag` | `Boolean` | absent | Remove |
| `source_type` | absent | `VARCHAR(80) NOT NULL INDEX` | Add |
| `title` | `VARCHAR(255)` | `VARCHAR(500) NOT NULL` | Widen + NOT NULL |
| `url_hash` | absent | `VARCHAR(64) NOT NULL UNIQUE` | Add |
| `source_quality` | `VARCHAR(40) default 'secondary_source'` | `VARCHAR(80) NOT NULL` | Widen + NOT NULL |
| `verified_flag` | `Boolean default False` | `Boolean NOT NULL default False` | Add NOT NULL |
| `public_visibility` | absent | `Boolean NOT NULL default False INDEX` | Add |
| `review_status` | absent | `VARCHAR(80) NOT NULL default 'pending_review' INDEX` | Add |
| `reviewed_at/by/notes` | absent | present | Add |
| `correction_note/dispute_note` | present | present | Match |

---

### `event_sources`
**Status: MATCH** — no drift detected.

---

### `outcomes`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `description` | `Text` | absent | Remove |
| `summary` | absent | `Text NOT NULL` | Add |
| `verified_source_id` | absent | `FK legal_sources.id NOT NULL` | Add |
| `outcome_type` | `VARCHAR(80)` | `VARCHAR(120)` | Widen |

---

### `evidence_reviews`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `decision` | `VARCHAR(40)` | absent | Remove |
| `previous_status` | absent | `VARCHAR(80)` | Add |
| `new_status` | absent | `VARCHAR(80) NOT NULL INDEX` | Add |
| `notes` | absent | `Text` | Add |
| `entity_type` | present | `NOT NULL INDEX` | Add NOT NULL |
| `reviewed_at` | present | `NOT NULL` | Add NOT NULL |

---

### `review_items`
**Status: SIGNIFICANT DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `item_type` | present | `record_type VARCHAR(80) NOT NULL INDEX` | Rename |
| `source_event_id` | `FK events.id` | `raw_source_id Integer INDEX` (no FK) | Replace |
| `suggested_event_type` | present | absent | Remove |
| `suggested_summary` | present | absent | Remove |
| `confidence_score` | `Float` | `confidence Float NOT NULL default 0.0` | Rename + NOT NULL |
| `ai_model` | present | absent | Remove |
| `status` | `VARCHAR(40) default 'pending'` | `VARCHAR(80) NOT NULL INDEX` | Widen + NOT NULL |
| `suggested_payload_json` | absent | `JSON NOT NULL` | Add |
| `source_url` | absent | `Text` | Add |
| `source_quality` | absent | `VARCHAR(80) NOT NULL INDEX` | Add |
| `privacy_status` | absent | `VARCHAR(80) NOT NULL INDEX` | Add |
| `publish_recommendation` | absent | `VARCHAR(80) NOT NULL INDEX` | Add |
| `reviewer_id` | absent | `VARCHAR(120)` | Add |
| `reviewer_notes` | absent | `Text` | Add |
| `reviewed_at` | absent | `DateTime` | Add |

---

### `review_action_logs`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `performed_by` | `VARCHAR(120)` | `actor VARCHAR(120) NOT NULL INDEX` | Rename + NOT NULL |
| `performed_at` | `DateTime server_default` | `created_at DateTime server_default` | Rename |
| `note` | `Text` | absent | Remove |
| `action` | `VARCHAR(80)` | `VARCHAR(80) NOT NULL INDEX` | Add NOT NULL + index |
| `before_json` | absent | `JSON` | Add |
| `after_json` | absent | `JSON` | Add |

---

### `crime_incidents`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `incident_category` | nullable | `NOT NULL INDEX` | Add NOT NULL |
| `source_id` | `VARCHAR(255)` | `VARCHAR(120) INDEX` | Narrow |
| `external_id` | `VARCHAR(255) NOT NULL` | `VARCHAR(120) INDEX` (nullable) | Narrow + remove NOT NULL |
| `source_name` | `VARCHAR(80)` | `VARCHAR(255) NOT NULL INDEX` | Widen + NOT NULL |
| `review_status` | `VARCHAR(40)` | `VARCHAR(80) NOT NULL INDEX` | Widen + NOT NULL |
| `reviewed_at/by/notes` | absent | present | Add |
| `correction_note/dispute_note` | absent | present | Add |
| `created_at/updated_at` | absent | present (TimestampMixin) | Add |
| UniqueConstraint | `(source_name, external_id)` | same | Match |

---

### `ingestion_runs`
**Status: DRIFT**

| Column | Migration | ORM | Fix |
|---|---|---|---|
| `created_at/updated_at` | absent | present (TimestampMixin) | Add |
| `source_name` | `VARCHAR(80)` | `VARCHAR(120)` | Widen |
| `status` | `VARCHAR(40) NOT NULL` | `VARCHAR(80) default 'running'` | Widen |

---

### `audit_logs`
**Status: MATCH** — no drift detected.

---

## schema_compat.py Decision

`schema_compat.py` exists to patch live databases created by the old migration. After the migration is corrected it should:
1. Remain in the codebase as documentation of what was wrong.
2. Be **removed from the startup call** in `main.py`.
3. Be annotated clearly as legacy-only, never called in clean-install paths.

---

## Summary of Required Actions

1. Rewrite the single Alembic migration to match the ORM exactly.
2. Remove `ensure_prototype_schema_compat` from `main.py` startup.
3. Annotate `schema_compat.py` as legacy-only.
4. Verify `alembic upgrade head` against a fresh SQLite DB passes.
5. Run `pytest` to confirm ORM/migration alignment.
