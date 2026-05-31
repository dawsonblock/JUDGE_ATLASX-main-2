# THE-JUDGE: PII Policy

This document describes how the platform handles personally identifiable information (PII), including special categories of sensitive data.

---

## Scope

THE-JUDGE focuses exclusively on public officials (judges) acting in their official, public capacity. Despite this narrow scope, PII risks exist because:

- Court records sometimes contain defendant, witness, and victim names
- Addresses and contact information appear in some public records
- Some records involve minors or other protected categories

---

## What We Store

We store only information that is:

1. Part of the officially published public court record, **and**
2. Directly relevant to the judge's official conduct or decisions, **and**
3. Not subject to a sealing, expungement, or publication ban order

We do **not** store:
- Home addresses of any individual
- Private contact information
- Financial information beyond what appears in official public records
- Health information
- Social Insurance Numbers (SIN), Social Security Numbers (SSN), or government ID numbers

---

## Special Categories

### Juvenile Records

Records involving minors are **never** published and must not be ingested. If a record is identified as involving a minor:
- The record is immediately quarantined with status `quarantined`
- A note is added to the audit log
- The owner is notified
- The source snapshot is retained for legal compliance purposes but the record is never made public

### Sealed and Expunged Records

If a record that was previously public is subsequently sealed or expunged:
- The record is immediately set to `review_status=removed_from_public` and `public_visibility=False`
- The takedown is logged in the audit log with the legal basis
- The snapshot is retained for legal compliance purposes only
- No further ingestion from the same source document is permitted

### Publication Bans

Canadian courts may issue publication bans (e.g., under s.486 Criminal Code). If a publication ban is identified:
- The affected records are immediately removed from public visibility
- The ban is recorded in the source registry
- Ingestion from the affected proceedings is blocked

---

## Minimisation Principles

1. **Collect minimum necessary** — ingest only the fields required for the platform's purpose
2. **No defendant names** — names of defendants, accused persons, or victims are not stored unless they are also a public official acting in their official capacity
3. **No residential addresses** — location data is stored only at city/region precision for crime statistics
4. **No biometric data** — photos, fingerprints, DNA references are never stored
5. **Aggregate over individual** — where statistics are sufficient, do not store individual records

---

## Retention Limits

| Data Category | Retention |
|---------------|-----------|
| Public court records | Indefinitely (or until valid takedown) |
| Ingestion snapshots | Until associated record is removed |
| Audit logs | 7 years |
| PII in ingestion staging | 30 days (then anonymised or deleted) |
| Reviewer notes | Until record is removed |

---

## Access Controls

- PII-containing fields are accessible only to reviewers and above.
- Public API responses never include raw PII fields (addresses, full names of non-public-figures).
- Evidence snapshots are stored in a separate evidence vault with access logging.

---

## Breach Response

If a PII breach is identified:
1. Immediately revoke public visibility for affected records
2. Notify the owner within 1 hour
3. Document the breach in the audit log
4. Assess whether notification obligations apply (PIPEDA / provincial privacy law)
5. Implement remediation within 72 hours

---

## Legal Basis (Canada)

Data processing is conducted under:
- **PIPEDA** (Personal Information Protection and Electronic Documents Act) where applicable
- **Provincial privacy laws** where more restrictive
- **Court publication rules** — we follow all court-ordered publication restrictions

---

## Questions

Privacy questions: see `CORRECTION_AND_TAKEDOWN.md` for the submission process.
