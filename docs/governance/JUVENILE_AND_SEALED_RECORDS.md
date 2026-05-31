# Juvenile Records and Sealed / Expunged Records Policy

> **Status:** Draft — requires legal review before public deployment.  
> **Scope:** Applies to all records involving persons under 18 at the time of the proceedings, and all records subject to sealing, expungement, or publication-ban orders.

---

## 1. Purpose

This policy defines how THE-JUDGE platform handles:
- Records involving individuals who were under 18 at the time of the events
- Records subject to court-ordered sealing or expungement
- Records subject to publication bans
- Records involving young persons under the *Youth Criminal Justice Act* (YCJA)

These categories require heightened protection because:
- Publication of youth records is a criminal offence under YCJA s. 110
- Sealed records represent a judicial determination that the public interest in disclosure is outweighed by harm
- Expunged records legally no longer exist for most purposes

---

## 2. Youth Records (YCJA)

### 2.1 Absolute Prohibition

The platform **must not publish any record** that identifies a young person (under 18 at time of offence) in connection with a YCJA proceeding.

This prohibition applies regardless of:
- Whether the information is technically available in public databases
- Whether the young person's name appears elsewhere online
- Whether the young person is now an adult

### 2.2 Detection

Ingest pipelines must flag records involving youth proceedings:
- Case citations containing "Youth" or "Young Person" in the title
- YCJA-specific court databases (e.g., CanLII entries tagged as youth matters)
- Source records explicitly marked as youth court

Flagged records must be set to `visibility_state = blocked` with `block_reason = "youth_record_suspected"` and queued for human reviewer assessment.

### 2.3 When in Doubt

If a reviewer cannot confirm that a record does NOT involve a young person, the record must remain blocked. The default for ambiguous records is **non-publication**.

### 2.4 Accidental Publication

If a youth record is accidentally published:
1. Retract immediately (set `visibility_state = retracted`)
2. Notify the platform operator
3. Notify legal counsel
4. Write a chain-of-custody event with full incident details
5. Retain the retracted record for internal audit only
6. Do NOT hard-delete until legal counsel confirms it is safe to do so

---

## 3. Sealed Records

### 3.1 What "Sealed" Means

A sealed court record is one that a court has ordered to be withheld from public access. The reasons may include:
- Protection of a witness or informant
- National security
- Protection of the identity of a victim
- Ongoing investigation

### 3.2 Platform Obligations

If a record in the platform becomes subject to a sealing order:
1. **Immediate action:** Set `visibility_state = blocked`, `block_reason = "sealing_order"`
2. **Within 24 hours:** Complete the retraction workflow
3. **Chain of custody:** Record the court order details, date, and issuing court
4. **Operator notification:** Notify the platform operator
5. **Legal hold:** Place a legal hold on the chain-of-custody log for this record

The platform **must not** retain a copy of sealed content for public access purposes, even in backups used for public queries.

---

## 4. Expunged Records

### 4.1 What "Expunged" Means

An expunged record is one that has been legally destroyed or erased by court order. Under Canadian law, a record suspension (*formerly pardon*) does not automatically expunge records, but an expungement order under the *Expungement of Historically Unjust Convictions Act* (EHUJCA) does.

### 4.2 Platform Obligations

If a record is subject to a valid expungement order:
1. **Hard delete** the published record and all linked evidence snapshots
2. The deletion must be logged in a restricted-access audit record
3. The deletion record itself must not be publicly accessible
4. Backups containing the expunged record must be marked for expiry

Hard delete of an expunged record is the **only** case where hard delete of a published record is permitted without a retention waiting period.

---

## 5. Publication Bans

Canadian courts routinely issue publication bans under the *Criminal Code*, the *Canada Evidence Act*, and other statutes. Common publication bans include:
- s. 486.4 — victim or witness identity in sexual offence proceedings
- s. 517 — bail hearing contents
- s. 539 — preliminary inquiry evidence

### 5.1 Automatic Triggering

Source adapters must flag records that match known publication-ban patterns:
- Records from sexual offence proceedings (source category: `sexual_offence`)
- Records from bail hearings
- Records from preliminary inquiries

Flagged records are blocked by default and require explicit reviewer confirmation that no publication ban applies before they can be published.

### 5.2 Reviewer Responsibility

Reviewers must confirm the absence of a publication ban before approving publication. The review checklist must include a publication-ban confirmation step.

---

## 6. Workflow Summary

```
Ingest → Flag (youth / sealed / ban suspected)
       → Block (visibility_state = blocked)
       → Human reviewer assessment
           ├── Confirmed no restriction → unblock, proceed to normal review
           ├── Restriction confirmed → retract, notify operator, legal hold
           └── Ambiguous → remain blocked pending legal guidance
```

---

## 7. Technical Enforcement

The evidence publication gate (`is_publishable()`) must block publication for:
- `block_reason = "youth_record_suspected"`
- `block_reason = "sealing_order"`
- `block_reason = "publication_ban"`
- Any record with `review_status = "blocked"`

No bypass mechanism exists for these states. Unblocking requires a human reviewer action that writes a chain-of-custody event.

---

## 8. Reporting

The platform operator must maintain a log of:
- All records blocked for youth/sealed/ban reasons
- All unblock decisions (with reviewer ID and justification)
- All accidental publications and remediation actions
- All court orders received and acted upon

---

## 9. Contacts and Escalation

When a court order affecting records is received:
1. Do not act without legal counsel confirmation
2. Contact the designated legal contact for the platform
3. Document the order and communication chain
4. Act on legal counsel's instruction, not on informal requests

---

*See also: [PII_POLICY.md](PII_POLICY.md), [RETENTION_POLICY.md](RETENTION_POLICY.md), [LEGAL_RISK_BOUNDARIES.md](LEGAL_RISK_BOUNDARIES.md)*
