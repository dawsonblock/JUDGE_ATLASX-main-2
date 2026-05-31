# AI Boundary Warning

**This is a legal-domain application. The following constraints are non-negotiable.**

---

## What This System Does NOT Do

JUDGE ATLAS does **not** use AI or machine learning to:

- Make determinations of guilt or innocence
- Predict judicial outcomes
- Assess the credibility of witnesses or parties
- Generate legal opinions or advice
- Score or rank individuals in ways that could affect legal proceedings
- Infer protected characteristics (race, religion, gender, etc.) from legal records

---

## What This System DOES Do (AI-Assisted)

The AI-adjacent modules in `backend/app/ai/` are **rule-based, deterministic** utilities:

| Module | Purpose | No LLM calls |
|---|---|---|
| `source_perspective_assistance.py` | Keyword-based perspective indicators per source | ✅ |
| `evidence_support_weighting.py` | Deterministic trust-score propagation through graph edges | ✅ |
| `narrative_pattern_assistance.py` | Pattern detection across entity claims (rule-based) | ✅ |

None of these modules make network calls, invoke language models, or produce probabilistic judgements.

---

## Bias and Fairness

The word "bias" has been intentionally removed from module names. Rule-based source perspective indicators describe structural properties of sources (e.g., prosecutorial vs. defense-oriented language patterns), not the bias of individuals.

Users of this system must not:
- Treat source perspective indicators as objective truth about source reliability
- Use these outputs to disadvantage individuals in legal contexts without human review
- Present automated outputs as judicial determinations

---

## Audit Requirements

All mutations to judicial data require:
1. Human review (see `backend/app/review/`)
2. Audit log entries (see `backend/app/audit/`)
3. Evidence chain documentation (see `docs/EVIDENCE_MODEL.md`)

See `tests/backend/test_audit_required_for_mutations.py` and `tests/backend/test_review_gate_publication.py` for the enforced contracts.

---

## Legal Scope

This system operates on **publicly available court records and legislation**. It does not process:
- Sealed or juvenile records (see `docs/JUVENILE_AND_SEALED_RECORDS.md`)
- Records outside Canada (current scope)
- Personal data beyond what is in public court records

For the full legal risk assessment, see `docs/security/LEGAL_RISK_BOUNDARIES.md`.
