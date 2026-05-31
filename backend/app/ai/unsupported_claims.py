"""Detect and flag AI claims that cannot be attributed to cited evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class UnsupportedClaimReport:
    total_claims: int
    unsupported: list[str] = field(default_factory=list)
    supported_ids: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.unsupported) == 0


def check_claims(
    claims: Sequence[str],
    cited_evidence_ids: Sequence[int],
    *,
    require_evidence: bool = True,
) -> UnsupportedClaimReport:
    """Flag any claim in *claims* when no evidence IDs are cited.

    When *require_evidence* is True and *cited_evidence_ids* is empty,
    every claim is considered unsupported.
    """
    unsupported: list[str] = []
    if require_evidence and not cited_evidence_ids:
        unsupported = list(claims)
    return UnsupportedClaimReport(
        total_claims=len(claims),
        unsupported=unsupported,
        supported_ids=list(cited_evidence_ids),
    )
