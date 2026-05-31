"""Ingestion-layer publication policy bridge.

Thin adapter between the ingestor pipeline and app.services.publish_rules.
This module is for **ingestion-time** tier classification only.

For display/API publication decisions use the canonical policy:
  ``app.policies.publication_policy.can_show_public_entity``
  ``app.policies.publication_policy.can_publish_entity``

Exposes:
  - PublicationDecision: typed result of publication gate evaluation
  - evaluate_publication_policy(record): run gate, return PublicationDecision
  - UNSAFE_MAP_PRECISIONS: re-exported for adapter use without deep service import
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.publish_rules import UNSAFE_MAP_PRECISIONS as UNSAFE_MAP_PRECISIONS
from app.services.publish_rules import is_publishable

__all__ = [
    "PublicationDecision",
    "evaluate_publication_policy",
    "UNSAFE_MAP_PRECISIONS",
]


@dataclass(frozen=True)
class PublicationDecision:
    """Typed result of the publication policy gate.

    Attributes:
        is_publishable: True if the record may be made public.
        blocking_reasons: Tuple of policy violation strings (empty when publishable).
    """

    is_publishable: bool
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_reason(self) -> str | None:
        """First blocking reason, or None when publishable."""
        return self.blocking_reasons[0] if self.blocking_reasons else None


def evaluate_publication_policy(record: Any) -> PublicationDecision:
    """Run the publication safety gate and return a typed PublicationDecision.

    Delegates to app.services.publish_rules.is_publishable and wraps the
    result.  Accepts any object or dict with publication-relevant fields:
    ``source_url``, ``source_tier``, ``precision_level``, ``review_status``,
    ``public_visibility``.

    A NormalizedIncident can be adapted by callers by mapping its ``precision``
    field to ``precision_level`` before calling.
    """
    ok, reasons = is_publishable(record)
    return PublicationDecision(
        is_publishable=ok,
        blocking_reasons=tuple(reasons),
    )
