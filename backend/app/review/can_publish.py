"""Compatibility wrapper for canonical publication policy.

New code should call :mod:`app.policies.publication_policy` directly.  This
module remains for older imports, but it no longer treats ReviewItem
``approved`` as entity publication authority.
"""

from __future__ import annotations

from app.policies.publication_policy import PUBLIC_REVIEW_STATUSES

APPROVED_STATUSES: frozenset[str] = frozenset(PUBLIC_REVIEW_STATUSES)


def can_publish(entity) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = getattr(entity, "review_status", None)
    if status not in PUBLIC_REVIEW_STATUSES:
        reasons.append(f"non_public_review_status:{status!r}")
    if getattr(entity, "public_visibility", None) == "private":
        reasons.append("public_visibility_private")
    return len(reasons) == 0, reasons
