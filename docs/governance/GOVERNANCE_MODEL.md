# THE-JUDGE: Governance Model

This document describes the governance structure, editorial policies, and accountability mechanisms for THE-JUDGE platform.

## Purpose

THE-JUDGE is a legal transparency research tool that aggregates and presents public records about judicial proceedings in Canada and internationally. It is not a news outlet, not a court, and not a law enforcement agency.

Every record on the platform exists to support public accountability for public figures (judges) in their official, public capacity. It is never a vehicle for harassment, personal attacks, or speculation about private individuals.

---

## Scope

THE-JUDGE covers:
- **Judicial decisions** — published, public court records
- **Court proceedings** — dockets, rulings, orders that are part of the public record
- **Official statistical data** — aggregated crime and court statistics from government sources
- **Public accountability events** — disciplinary proceedings, judicial council findings

THE-JUDGE does **not** cover:
- Private individuals who are not public officials
- Defendants, victims, or witnesses in proceedings (only judges in their official capacity)
- Sealed or expunged records
- Juvenile records or proceedings
- Records that have been ordered removed from public access

---

## Review and Publication Workflow

Every record follows this workflow before any public visibility:

1. **Ingestion** — Record is fetched from an authorised source with a snapshot and hash
2. **Pending review** — Record is held in `pending_review` state, not visible publicly
3. **Human review** — A qualified reviewer examines the record against the source evidence
4. **Reviewer decision** — Approve, reject, or flag for more sources
5. **Publication gate** — Publication is only permitted if all evidence gates pass (see `docs/EVIDENCE_MODEL.md`)
6. **Public visibility** — Record becomes visible only after all gates pass

**LLM assistance** may be used by reviewers to summarize evidence or flag contradictions, but LLM output alone is never sufficient to approve or publish a record.

---

## Roles and Responsibilities

| Role | Permissions | Accountability |
|------|-------------|----------------|
| `viewer` | Read public records only | N/A |
| `reviewer` | Approve/reject review items | Logged by name for every decision |
| `source_admin` | Manage source registrations, trigger ingestion | Logged for every source change |
| `admin` | All reviewer + source_admin permissions | All actions logged |
| `owner` | All admin permissions + user management | All actions logged; notified on governance disputes |

**Every mutation is logged to the AuditLog** with the actor's identity (email), role, timestamp, and the entity affected.

---

## Reviewer Accountability

- Reviewers must be registered users with verified email addresses.
- Every review decision is logged with the reviewer's identity.
- Reviewers may not approve records in which they have a personal interest.
- Reviewer decisions may be appealed by the subject of the record (see `CORRECTION_AND_TAKEDOWN.md`).
- Reviewer credentials may be revoked by an owner if misconduct is identified.

---

## Source Authority Hierarchy

Sources are classified by trust tier:

| Tier | Description | Examples |
|------|-------------|---------|
| `court_record` | Official, published court decisions | CanLII, CourtListener |
| `official_police_open_data` | Structured open-data police statistics | Saskatoon Police, Toronto Police |
| `official_government_statistics` | Aggregate government statistics | Statistics Canada, FBI UCR |
| `verified_news_context` | Verified news providing context only | Major news organisations |

Records from lower-trust tiers (news, scraped media) may never be published without a higher-trust primary source.

---

## Data Retention

- **Public records** are retained indefinitely unless subject to a valid takedown request (see below).
- **Ingestion run logs** are retained for 90 days.
- **Audit logs** are retained for 7 years (legal compliance).
- **Snapshots** are retained as long as the associated record is active.
- **PII** — see `PII_POLICY.md`.

---

## Dispute and Appeal Process

See `CORRECTION_AND_TAKEDOWN.md` for the full process.

Summary:
1. Subjects of records may submit a correction request identifying specific factual errors.
2. Takedown requests may be submitted where legal grounds exist.
3. Disputed records are flagged as `disputed` in the review status and removed from public visibility pending review.
4. The owner must respond to valid correction requests within 30 days.

---

## Conflicts of Interest

- No reviewer may review records involving themselves or their immediate family members.
- No reviewer may review records from a court or jurisdiction where they are employed.
- Conflicts must be disclosed and the record reassigned to another reviewer.

---

## Transparency

- The list of active data sources is public.
- The methodology and review standards are documented.
- Aggregate statistics about the review queue (counts only, no individual records) are public.
- The governance model and PII policy are public.

---

## Contact

Governance questions, corrections, and takedown requests:
See `CORRECTION_AND_TAKEDOWN.md` for submission procedures.
