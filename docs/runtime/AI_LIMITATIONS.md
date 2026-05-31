# AI Limitations

**Status: alpha — AI is a reviewer-assistance tool only**

---

## What AI Can Do

AI modules in THE-JUDGE are restricted to the following reviewer-assistance tasks:

| Task | Description |
|------|-------------|
| Extraction helper | Help parse structured fields from source text |
| Duplicate detection | Flag likely duplicate records for human review |
| Source comparison | Identify conflicts between sources |
| Summarization | Summarize a document for reviewer context |
| Anomaly flagging | Surface unusual or potentially erroneous data |
| Missing-evidence detection | Identify records lacking required evidence |

---

## What AI Must Never Do

The following tasks are **permanently forbidden** for AI components:

| Forbidden Task | Reason |
|----------------|--------|
| Guilt assignment | Legal determinations require human judgment |
| Legal conclusion as fact | AI cannot certify legal truth |
| Auto-publication | No record may be published without human reviewer approval |
| Criminality scoring | Scoring individuals for criminality is harmful and unsupported |
| Unsourced accusation | All claims must reference a verified source |
| Identity inference | AI must not infer or link identities without explicit evidence |

---

## AI Output Requirements

All AI-generated output must include:

1. **Confidence score** (0.0–1.0) — how certain the model is
2. **Citation** — reference to the source document that supports the output
3. **Provenance** — which prompt template and model version produced the output
4. **Reviewer flag** — output is marked as AI-suggested, not verified

---

## Prompt Templates

All prompt templates must:
- Require source citation in the output
- Explicitly instruct the model not to assign guilt or make legal determinations
- Include a provenance field (`prompt_version`, `model_name`)
- Not instruct the model to make public visibility decisions

Templates are stored in `app/ai/` and are versioned.

---

## Enforcement

The `AICorrectnessCheck` model stores AI output with:
- `prompt_version` — which template was used
- `model_name` — which model produced the output
- `source_supports_claim` — whether the AI verified a source supports its claim
- `duplicate_candidate` — deduplication flag (human must confirm)
- `map_quality` — AI assessment, not final determination
- No guilt score, no danger score, no criminality score

---

## Governance

AI output cannot:
- Directly mutate a `verified_flag=True` record
- Set `public_visibility=True` on any record
- Create `AuditLog` entries with `actor_type=ai` (future: may be allowed for traceability)

Human review is required before any AI-suggested change is applied to a published record.

---

## Alpha Warning

This is an **alpha** system. AI modules are experimental and may produce incorrect output. All AI output must be treated as unverified suggestions pending human review.
