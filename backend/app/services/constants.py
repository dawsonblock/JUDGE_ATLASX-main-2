from app.ingestion.statuses import PENDING
from app.policies.publication_policy import (
    NON_PUBLIC_REVIEW_STATUSES,  # noqa: F401 — re-exported for consumers
    PUBLIC_REVIEW_STATUSES,
    REJECTED,
    REMOVED_FROM_PUBLIC,
    REVIEW_STATUSES,
    VERIFIED_COURT_RECORD,
)

ALLOWED_EVENT_TYPES = {
    "detention_order",
    "release_order",
    "bond_modification",
    "sentencing",
    "probation_order",
    "supervised_release",
    "revocation",
    "resentencing",
    "published_opinion",
    "unpublished_opinion",
    "appeal_reversal",
    "appeal_affirmance",
    "appeal_remand",
    "indictment",
    "dismissal",
    "sentencing_recommendation",
    "motion_to_suppress",
    "mitigation_filing",
    "iac_finding",
    "judicial_misconduct_finding",
    "ethics_report",
    "press_release",
    "news_coverage",
}

ALLOWED_OUTCOME_TYPES = {
    "supervised_release_revocation",
    "new_federal_charge",
    "appeal_reversal",
    "appeal_modification",
    "resentencing",
    "probation_violation",
}

OUTCOME_UNKNOWN = "Outcome unknown — no public post-decision record located."

AI_PUBLISH_RECOMMENDATIONS = {
    "safe_auto_publish",
    "review_required",
    "block",
}

AI_REVIEW_ITEM_STATUSES = {
    PENDING,
    "approved",
    "rejected",
    "needs_more_sources",
    "blocked",
    "published",
}

REPEAT_OFFENDER_INDICATORS = [
    "prior conviction",
    "criminal history",
    "criminal history category",
    "career offender",
    "acca",
    "supervised release violation",
    "revocation",
    "danger to the community",
    "18 u.s.c. § 3142",
    "18 u.s.c. 3142",
]
