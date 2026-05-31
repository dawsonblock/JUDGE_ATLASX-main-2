# Data Retention Policy

> **Status:** Draft — requires legal review before public deployment.  
> **Scope:** Applies to all data stored or processed by THE-JUDGE platform.

---

## 1. Purpose

This policy defines how long different categories of data are retained, when they are deleted or anonymised, and who is responsible for enforcing these limits.

Retention must balance:
- **Accountability** — records of judicial conduct and public proceedings
- **Privacy** — personal information of individuals who appear in records
- **Legal obligations** — court records, freedom-of-information requirements, privacy legislation (PIPEDA, provincial equivalents)

---

## 2. Data Categories and Retention Periods

### 2.1 Public Court Records (ReviewItem)

| State | Retention | Notes |
|---|---|---|
| `pending_review` | 90 days from ingest, then delete unless promoted | Unpublished draft; no public access |
| `published` | 7 years from publication date | Legal proceeding records |
| `retracted` | 2 years after retraction | Retain chain-of-custody; anonymise personally identifying fields |
| `rejected` | 30 days from rejection | May be purged sooner on operator request |
| `sealed` / `expunged` | Delete immediately on court order | See JUVENILE_AND_SEALED_RECORDS.md |

### 2.2 Evidence Snapshots (EvidenceSnapshot)

Evidence snapshots must be retained as long as the linked `ReviewItem` is retained. They may not be deleted independently while the linked record is active or published.

- Hash verification must remain possible for the lifetime of the linked record.
- After the linked record is purged, snapshots may be deleted.

### 2.3 Audit Logs (AuditLog)

| Purpose | Retention |
|---|---|
| Standard mutation events | 3 years |
| Security/access events | 5 years |
| Logs linked to legal holds | Until hold is released + 1 year |

Audit logs must never be deleted to cover up errors; deletion requests must themselves be logged.

### 2.4 UserSession and Authentication Tokens

| Type | Retention |
|---|---|
| Active sessions | Until expiry or logout |
| Expired/revoked sessions | 90 days (for security analysis), then delete |
| Refresh token hashes | Deleted on `logout` or `logout-all` |

### 2.5 Chain-of-Custody Events

Chain-of-custody events are immutable and must be retained for the lifetime of the linked record plus 2 years.

---

## 3. Deletion and Anonymisation

### 3.1 Hard Delete

Hard delete (physical removal) is only permitted for:
- Juvenile records on court order (see JUVENILE_AND_SEALED_RECORDS.md)
- Sealed/expunged records on court order
- PII minimisation requests where the individual is not a public official acting in official capacity
- Expired `pending_review` drafts (90-day auto-purge)

All hard deletes must write a final chain-of-custody event before removal.

### 3.2 Soft Retraction

Published records that are disputed, corrected, or subject to a takedown request are **retracted**, not deleted. Retraction:
- Sets `visibility_state = retracted`
- Writes a chain-of-custody event with reason and actor
- Removes from all public views
- Preserves the audit trail

### 3.3 Anonymisation

When a published record must be retained for legal accountability but a specific individual requests PII removal:
- Names of private individuals (not public officials) may be anonymised to initials
- Anonymisation is a mutation that writes an audit log entry and chain-of-custody event
- The original name is retained in a restricted-access field for operator use
- Anonymisation does not apply to named public officials acting in their official role

---

## 4. Automated Retention Enforcement

The platform must implement scheduled retention enforcement:

```
judgectl retention run --dry-run   # preview what would be purged
judgectl retention run --commit    # execute purges with full audit trail
```

Purge jobs must:
- Log the number and type of records affected
- Never delete records that have open correction or takedown requests
- Never delete records subject to a legal hold
- Emit a summary report to `artifacts/retention/YYYY-MM-DD-retention-report.md`

---

## 5. Legal Holds

A legal hold prevents any automated or manual deletion of the affected records.

Legal holds may be placed by:
- Platform operators (manual)
- Court order (must be processed immediately)

A record under legal hold must display a visible indicator to internal reviewers.

---

## 6. Backup Retention

| Backup type | Retention |
|---|---|
| Daily database backups | 30 days |
| Weekly snapshots | 90 days |
| Pre-migration snapshots | 1 year |
| Disaster-recovery archive | 2 years |

Backups are subject to the same deletion rules as production data. Backup data must not be used to circumvent a deletion or anonymisation request.

---

## 7. Operator Responsibilities

The platform operator is responsible for:
- Running scheduled retention jobs at least monthly
- Reviewing the retention report for anomalies
- Escalating legal-hold requests to legal counsel
- Documenting any deviations from this policy

---

## 8. Review Schedule

This policy must be reviewed annually or after any significant change to:
- Applicable legislation (PIPEDA, provincial privacy law)
- The data model
- The jurisdiction scope of the platform

---

*See also: [PII_POLICY.md](PII_POLICY.md), [CORRECTION_AND_TAKEDOWN.md](CORRECTION_AND_TAKEDOWN.md), [GOVERNANCE_MODEL.md](GOVERNANCE_MODEL.md)*
