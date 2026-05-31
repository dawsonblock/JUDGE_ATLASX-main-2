"""Relationship arc publication policy.

Controls which ``EntityGraphEdge`` records can be exposed via the public
``/api/map/relationship-arcs`` endpoint.  Three gates must ALL pass:

1. The feature flag ``enable_public_relationship_arcs`` must be ``True``.
2. Each edge must carry at least ``public_relationship_arc_min_evidence``
   non-null evidence references.
3. The edge predicate must NOT match any causal/blame/guilt pattern.

Results are also hard-capped at ``public_relationship_arc_max_results``.

Design note: the policy is intentionally conservative — when in doubt,
exclude the edge.  Reviewers can loosen the predicate blocklist or increase
the evidence threshold via admin settings.  The feature flag prevents *all*
arcs from being published even when the other gates would pass, making it
safe to ship the endpoint before any arc data is ready for public use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.models.entities import EntityGraphEdge

# ---------------------------------------------------------------------------
# Causal / blame / guilt label blocklist
# Predicates matching any of these sub-patterns are excluded from public output
# regardless of evidence count or review status.
# ---------------------------------------------------------------------------
_CAUSAL_SUB_PATTERNS: tuple[str, ...] = (
    "caus",         # cause, caused, causing
    "blam",         # blame, blamed, blaming
    "guilt",        # guilty, guilt
    "corrupt",      # corrupt, corrupted, corruption
    "conspir",      # conspire, conspired, conspiracy
    "murder",       # murder, murdered
    r"\bkill",      # kill, killed (word-boundary prefix to avoid "skill")
    "assault",      # assault, assaulted
    "abus",         # abuse, abused, abusing
    "harass",       # harass, harassed, harassment
    "defam",        # defame, defamed, defamation
    "threaten",     # threaten, threatened
    "bribe",        # bribe, bribery
    "defraud",      # defraud, defrauded
    "misconduct",   # misconduct
    "criminaliz",   # criminalize
    "convict",      # convict, convicted
    "condemn",      # condemn, condemned
    "perpetrat",    # perpetrate, perpetrated
    "orchestrat",   # orchestrate
)

_CAUSAL_LABEL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pat, re.IGNORECASE) for pat in _CAUSAL_SUB_PATTERNS
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArcPolicyResult:
    """Outcome of evaluating a set of relationship arc edges through policy.

    Attributes:
        allowed:        True if at least one edge passed all gates.
        arcs_enabled:   Reflects whether the feature flag is on.  False means
                        the endpoint is intentionally dark regardless of edges.
        reason:         Human-readable summary for logging / debug headers.
        filtered_edges: Subset of input edges that passed all gates, capped at
                        the configured maximum.  Empty list when not allowed.
    """

    allowed: bool
    arcs_enabled: bool
    reason: str
    filtered_edges: list = field(default_factory=list)


def _has_causal_label(predicate: str) -> bool:
    """Return True if *predicate* matches any causal/blame/guilt pattern."""
    return any(pat.search(predicate) for pat in _CAUSAL_LABEL_PATTERNS)


def _evidence_count(edge: "EntityGraphEdge") -> int:
    """Return the number of evidence references attached to *edge*."""
    refs = edge.evidence_refs
    if not refs:
        return 0
    if isinstance(refs, list):
        return len(refs)
    # Unexpected shape — be conservative
    return 0


def evaluate_arc_request(
    edges: "list[EntityGraphEdge]",
    settings: "Settings",
) -> ArcPolicyResult:
    """Evaluate *edges* through the publication policy gates.

    Args:
        edges:    Raw edges fetched from the database (already filtered for
                  ``status == "active"``).
        settings: Application settings carrying the three policy knobs.

    Returns:
        :class:`ArcPolicyResult` with ``filtered_edges`` and metadata flags.
    """
    # Gate 1 — feature flag
    if not settings.enable_public_relationship_arcs:
        return ArcPolicyResult(
            allowed=False,
            arcs_enabled=False,
            reason="feature disabled (enable_public_relationship_arcs=False)",
            filtered_edges=[],
        )

    min_evidence: int = settings.public_relationship_arc_min_evidence
    max_results: int = settings.public_relationship_arc_max_results

    passed: list = []
    skipped_evidence = 0
    skipped_causal = 0

    for edge in edges:
        # Gate 2 — minimum evidence threshold
        if _evidence_count(edge) < min_evidence:
            skipped_evidence += 1
            continue

        # Gate 3 — causal/blame/guilt label check
        if _has_causal_label(edge.predicate):
            skipped_causal += 1
            continue

        passed.append(edge)
        if len(passed) >= max_results:
            break

    parts: list[str] = []
    if skipped_evidence:
        parts.append(
            f"{skipped_evidence} edge(s) below min-evidence threshold ({min_evidence})"
        )
    if skipped_causal:
        parts.append(f"{skipped_causal} edge(s) excluded for causal/blame label")
    if not passed:
        parts.append("no edges passed all gates")

    return ArcPolicyResult(
        allowed=len(passed) > 0,
        arcs_enabled=True,
        reason="; ".join(parts) if parts else f"{len(passed)} edge(s) passed",
        filtered_edges=passed,
    )
