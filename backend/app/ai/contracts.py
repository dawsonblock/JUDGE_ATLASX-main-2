"""Contracts for AI module boundaries.

AI operations in JUDGE_ATLAS are bounded by these rules:
1. AI may only summarize evidence that has an evidence_id (source_snapshot_id).
2. AI must flag any claim it cannot support with a cited evidence_id.
3. AI output is NEVER published without human review.
4. AI must not make guilt, liability, or criminal-responsibility assertions.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIBoundaryContract:
    """Defines allowable inputs and output constraints for one AI operation."""

    operation: str
    requires_evidence_ids: bool = True
    output_requires_review: bool = True
    may_assert_guilt: bool = False
    may_assert_liability: bool = False
    supported_record_types: list[str] = field(default_factory=list)
    notes: str = ""

    def validate(self) -> list[str]:
        """Return list of violation strings (empty = valid)."""
        violations: list[str] = []
        if self.may_assert_guilt:
            violations.append(f"{self.operation}: may_assert_guilt must be False")
        if self.may_assert_liability:
            violations.append(f"{self.operation}: may_assert_liability must be False")
        if not self.output_requires_review:
            violations.append(
                f"{self.operation}: output_requires_review must be True — AI output cannot bypass review"
            )
        return violations


# Canonical registered AI operation contracts
REGISTERED_AI_CONTRACTS: list[AIBoundaryContract] = [
    AIBoundaryContract(
        operation="summarize",
        requires_evidence_ids=True,
        output_requires_review=True,
        supported_record_types=["CrimeIncident", "ReviewItem"],
        notes="Summarize raw evidence for reviewer consumption only",
    ),
    AIBoundaryContract(
        operation="classify",
        requires_evidence_ids=True,
        output_requires_review=True,
        supported_record_types=["ReviewItem"],
        notes="Suggest record_type classification; reviewer must confirm",
    ),
    AIBoundaryContract(
        operation="confidence_score",
        requires_evidence_ids=True,
        output_requires_review=True,
        supported_record_types=["ReviewItem"],
        notes="Estimate confidence 0–1; used as advisory signal only",
    ),
    AIBoundaryContract(
        operation="entity_resolution",
        requires_evidence_ids=True,
        output_requires_review=True,
        supported_record_types=["CrimeIncident"],
        notes="Suggest entity links; reviewer must approve",
    ),
]


def validate_all_contracts() -> list[str]:
    """Return all violations across all registered contracts."""
    violations: list[str] = []
    for contract in REGISTERED_AI_CONTRACTS:
        violations.extend(contract.validate())
    return violations
