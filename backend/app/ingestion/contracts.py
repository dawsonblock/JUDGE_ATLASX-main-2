"""Typed ingestion/source governance contracts.

These contracts are intentionally explicit and deterministic. They do not
trigger side effects and are used to validate source definitions before a
source can be considered runnable.
"""

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field


class IngestionMode(StrEnum):
    MACHINE_INGEST = "machine_ingest"
    PORTAL_REFERENCE = "portal_reference"
    MANUAL_REVIEW = "manual_review"
    DISABLED = "disabled"
    EXPERIMENTAL = "experimental"


class IngestCapability(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"
    SNAPSHOT = "snapshot"
    DEDUPE = "dedupe"


class ReviewRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class PublicationPolicy(StrEnum):
    NEVER_AUTOPUBLISH = "never_autopublish"
    REVIEW_GATED = "review_gated"


class SnapshotPolicy(StrEnum):
    REQUIRED = "required"


class SourceDefinition(BaseModel):
    source_key: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    ingestion_mode: IngestionMode
    trust_tier: str = Field(min_length=1)
    legal_restrictions: list[str] = Field(default_factory=list)
    retention_policy: str = Field(min_length=1)
    ingest_capabilities: list[IngestCapability] = Field(default_factory=list)
    review_requirement: ReviewRequirement = ReviewRequirement.REQUIRED
    publication_policy: PublicationPolicy = PublicationPolicy.REVIEW_GATED
    snapshot_policy: SnapshotPolicy = SnapshotPolicy.REQUIRED

    def validate_runnable(self) -> list[str]:
        """Return contract violations for runnable sources.

        A source is considered runnable only when it is machine_ingest and has
        fetch/parse/snapshot capabilities.
        """
        violations: list[str] = []
        if self.ingestion_mode != IngestionMode.MACHINE_INGEST:
            return violations

        required = {
            IngestCapability.FETCH,
            IngestCapability.PARSE,
            IngestCapability.SNAPSHOT,
        }
        present = set(self.ingest_capabilities)
        missing = sorted(cap.value for cap in (required - present))
        if missing:
            violations.append(f"missing_capabilities:{','.join(missing)}")

        if self.snapshot_policy != SnapshotPolicy.REQUIRED:
            violations.append("snapshot_policy_must_be_required")

        if self.publication_policy not in (
            PublicationPolicy.REVIEW_GATED,
            PublicationPolicy.NEVER_AUTOPUBLISH,
        ):
            violations.append("invalid_publication_policy")

        return violations
