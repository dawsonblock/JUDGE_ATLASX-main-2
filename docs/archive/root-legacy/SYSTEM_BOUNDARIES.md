# SYSTEM BOUNDARIES

## Purpose
JUDGE is an evidence-linked, review-gated atlas for civic/legal records. It is not a decision engine.

## In Scope
- Collect source snapshots from governed source definitions.
- Preserve immutable evidence lineage (snapshot hash, retrieval metadata, provenance).
- Produce derived records that always reference source evidence.
- Require explicit human review before publication of actionable outcomes.
- Provide auditable operator/admin actions.

## Out of Scope
- Autonomous legal adjudication.
- Sentencing or enforcement recommendations.
- Predictive policing/risk scoring on individuals.
- Automatic publication of unreviewed allegations.
- Opaque model-only assertions without evidence references.

## Authority Separation
- Evidence layer: canonical, immutable snapshots.
- Memory layer: derivative/search acceleration only.
- AI layer: assistive extraction/summarization only.
- Publication authority: human reviewer decision.
