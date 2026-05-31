# THE-JUDGE: Correction and Takedown Policy

This document describes the process for requesting corrections to records on THE-JUDGE platform, and for requesting the removal of records.

---

## Overview

THE-JUDGE is committed to accuracy and to minimising harm. If you believe a record is inaccurate, misleading, or should be removed, this document explains how to submit a request and what to expect.

---

## Who Can Submit Requests

- **The subject of a record** (the judge whose proceedings are described)
- **A legal representative** acting on behalf of the subject
- **A court officer** notifying us of a sealing order or publication ban
- **Anyone** who identifies a genuine factual error or legal compliance issue

---

## Types of Requests

### 1. Correction Request

A correction request identifies a **specific factual error** in a published record.

Examples:
- Incorrect case citation
- Wrong date
- Misidentified court
- Incorrect decision description

**What we will do:**
1. Acknowledge receipt within 5 business days
2. Review the correction against the source evidence
3. If the error is confirmed: correct the record, add a correction note, and update the audit log
4. If the error is disputed: flag the record as `disputed` and remove it from public view pending investigation
5. Notify the requester of the outcome within 30 days

**What we will not do:**
- Remove factually accurate records because the subject finds them unflattering
- Change records without evidence supporting the correction

---

### 2. Takedown Request

A takedown request asks for a record to be **removed entirely** from public visibility.

Valid grounds for takedown:
- Court order (sealing, publication ban, expungement)
- Record relates to a minor
- The record contains a material factual error that cannot be corrected in place
- Record was sourced in error (e.g., from a sealed document)
- PIPEDA / privacy law obligation

**Invalid grounds for takedown:**
- General discomfort with accurate public information
- The record is embarrassing but accurate
- The subject changed jobs or retired

**Process:**
1. Submit a takedown request with supporting documentation (court order, legal basis)
2. Acknowledge receipt within 2 business days
3. If a court order is provided: record is immediately removed from public visibility pending review
4. Legal review within 10 business days
5. Decision communicated to requester with reasons

---

### 3. Dispute Request

A dispute request flags a record as contested without identifying a specific error.

The record will be:
- Flagged as `disputed` in its review status
- Removed from public visibility while the dispute is active
- Reviewed by a senior reviewer within 30 days
- Either reinstated with a dispute note, corrected, or removed

---

### 4. PII Removal Request

If a record contains personal information (address, phone number, SIN/SSN) that should not be public:
- Submit a PII removal request with the specific field and the record identifier
- PII will be redacted within 48 hours pending confirmation it is not part of the official public record

---

## Sealed and Expunged Records

If a record is sealed or expunged by a court after it appeared on the platform:
- We require a copy of the court order
- The record is immediately removed from public visibility upon receipt of the order
- The snapshot is retained for legal compliance only and is not accessible via the API
- A note is added to the audit log

---

## Source Dispute Handling

If a data source is providing inaccurate or improperly collected data:
- Report the source dispute through the same process
- The source will be flagged as `disputed` in the source registry
- No new records from the source will be published until the dispute is resolved
- An owner will review the source trust classification

---

## Submission

To submit a correction, takedown, dispute, or PII removal request:

1. Create an issue in the project's issue tracker with the label `governance/correction` or `governance/takedown`
2. Include: the record URL or ID, the specific issue, and any supporting documentation
3. If the matter is legally sensitive, contact the owner directly (do not post sensitive legal documents publicly)

---

## Appeals

If you disagree with the outcome of a correction or takedown review:
- You may appeal to the owner within 30 days of the decision
- The owner's decision is final at the platform level
- You retain the right to pursue legal remedies independently of this process

---

## Accountability

All correction and takedown requests are logged (with the subject's consent) and the outcomes are tracked. Aggregate statistics (number of requests, resolution rates) are published annually.

---

## Defamation Risk

See `LEGAL_RISK_BOUNDARIES.md` for guidance on defamation and related legal risks.
