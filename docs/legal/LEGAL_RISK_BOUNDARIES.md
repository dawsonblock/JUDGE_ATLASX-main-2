# THE-JUDGE: Legal Risk Boundaries

This document describes the legal risk framework for the THE-JUDGE platform, including defamation risk, privacy risk, and areas where the platform explicitly limits its scope to reduce legal exposure.

---

## Disclaimer

**This document is not legal advice.** It is an internal policy document describing how this platform attempts to reduce legal risk. Operators should consult qualified legal counsel before deploying the platform in any jurisdiction.

---

## Core Legal Principle

THE-JUDGE is a **transparency platform for public records**, not:
- An investigative journalism outlet
- A law enforcement database
- A criminal records registry
- A defamation risk to public figures acting in their official capacity

The platform publishes only what courts, governments, and official bodies have already made public. It does not make original claims, draw conclusions, or characterise individuals.

---

## Defamation Risk

### What We Do to Mitigate Defamation Risk

1. **Only publish verified, sourced records** — Every published record must have a source URL, a source snapshot, and a verified review status.
2. **No original editorialising** — The platform does not add commentary, characterisation, or conclusions to records.
3. **No guilt inferences** — The system explicitly forbids LLM and automated tools from assigning guilt or inferring criminality.
4. **Disputed records are immediately hidden** — If a record is contested, it is removed from public view pending investigation.
5. **Correction mechanism** — We provide a correction and takedown process (see `CORRECTION_AND_TAKEDOWN.md`).
6. **Source authority hierarchy** — Lower-trust sources (news, social media) cannot stand alone; they require official primary sources.

### High-Risk Scenarios to Avoid

| Scenario | Risk | Policy |
|----------|------|--------|
| Publishing accusation without conviction | Defamation | **Blocked** — only verified court records |
| Naming defendants / victims in incidents | Privacy / defamation | **Blocked** — non-public figures excluded |
| AI-generated summaries presented as fact | Defamation | **Blocked** — LLM output is never published directly |
| Approximate locations presented as exact | Misleading | **Blocked** — approximate locations are labelled |
| Aggregate statistics used to profile individuals | Privacy | **Blocked** — aggregates are never linked to individuals |

---

## Privacy Risk (Canada)

### PIPEDA Compliance

Under PIPEDA, we process information about public officials in their official capacity, which is generally outside PIPEDA's scope. However:
- We do not store, process, or publish private contact information
- We honour takedown requests where PIPEDA obligations apply
- We conduct a Privacy Impact Assessment before adding new data categories

### Provincial Privacy Laws

Some provinces (Quebec, Alberta, British Columbia) have substantially equivalent privacy laws. We apply the most restrictive standard across all provinces.

### Publication Bans and s.517 Criminal Code

Canadian courts may order publication bans. We:
- Monitor known sources for publication ban orders
- Immediately remove affected content when a ban is identified
- Do not contest valid court orders

---

## Juvenile Records

The Youth Criminal Justice Act (YCJA) strictly limits publication of information identifying a young person involved in proceedings. We:
- Never knowingly publish records involving minors
- Quarantine any record that appears to involve a minor pending review
- Treat any uncertainty about age as a basis for quarantine

---

## Sealed and Expunged Records

Court orders sealing or expunging records supersede any prior public access. We:
- Honour all valid sealing and expungement orders
- Retain the snapshot for legal compliance only (not publicly accessible)
- Do not interpret the sealing order; if the order is ambiguous, we default to removal

---

## Jurisdictional Scope

Currently:
- **Canada** — Primary jurisdiction. We follow Canadian federal and provincial law.
- **United States** — Secondary jurisdiction for CourtListener data. We follow applicable US law.

We do not process records from jurisdictions where our legal position is unclear.

---

## AI and Legal Conclusions

The platform uses LLM tools only as reviewer assistance (never for publication decisions). Specifically:
- LLM output is never presented to end users as a factual conclusion
- LLM output is never sufficient to approve or publish a record
- LLM tools are prohibited from assigning guilt, inferring criminality, or scoring dangerousness
- All LLM responses require citation to specific source evidence

This architecture is documented in `docs/ARCHITECTURE_GATE.md` and enforced in `backend/app/llm/`.

---

## Map Display and Certainty

Maps can mislead users into believing information is more certain than it is. We:
- Label approximate locations visually differently from precise locations
- Display verification status on every map marker
- Distinguish court records from police incident statistics
- Exclude records without coordinates from map display
- Show confidence, source type, and evidence count on every marker

---

## Defamation Response

If we receive a defamation claim:
1. The subject record is immediately hidden from public view
2. Legal review is initiated within 48 hours
3. We do not remove records solely because of a legal threat; we evaluate the merits
4. We cooperate with valid court orders

---

## Limitations of This Policy

This policy does not:
- Eliminate legal risk entirely
- Substitute for qualified legal advice
- Cover all jurisdictions where the platform might be accessed
- Guarantee that all ingested records are legally safe to publish

Operators use this platform at their own legal risk and are responsible for compliance with applicable law in their jurisdiction.
