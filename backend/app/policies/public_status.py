"""Canonical public visibility and review-status constants.

These constants are the single source of truth for map/public-facing status
checks. Keep DB status values and report labels separate:
- DB lifecycle values: runnable, runnable_disabled, deprecated, etc.
- report labels: runnable_now, enable_ready
"""

from __future__ import annotations

PUBLIC_PRIVATE = "private"
PUBLIC_ADMIN_ONLY = "admin_only"
PUBLIC_SAFE = "public_safe"
PUBLIC_REDACTED = "public_redacted"
PUBLIC_BLOCKED = "blocked"

PUBLIC_VISIBLE_STATUSES = frozenset({PUBLIC_SAFE, PUBLIC_REDACTED})
NON_PUBLIC_STATUSES = frozenset({PUBLIC_PRIVATE, PUBLIC_ADMIN_ONLY, PUBLIC_BLOCKED})

REVIEW_APPROVED = "approved"
REVIEW_PENDING = "needs_review"
REVIEW_REJECTED = "rejected"
