"""Canonical entity resolver for deduplication across sources.

Resolves entities (judges, courts, cases, defendants, incidents) to canonical
identities with confidence scoring and merge proposal workflows.

NOTE: Authoritative resolver implementation now lives in app.graph.
This service re-exports the canonical classes below and retains its own
legacy helpers for backward compatibility.
"""

from __future__ import annotations

# Shim: expose graph-package classes through this module
from app.graph.graph_resolver import (
    GraphResolver,
    ResolveResult as GraphResolveResult,
)  # noqa: F401

import difflib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity, EntitySourceRecord

if TYPE_CHECKING:
    from app.models.entities import Judge, Court, Case


@dataclass
class MatchResult:
    """Result of an entity matching attempt."""

    canonical_entity_id: int | None
    confidence: float  # 0.0-1.0
    match_reason: str  # "exact_name", "fuzzy_match_95", etc.
    suggested_merge: bool = False


@dataclass
class MergeProposal:
    """Proposal to merge multiple entities into one canonical identity."""

    entity_ids: list[int]
    target_canonical_id: int
    confidence: float
    reason: str
    proposed_at: datetime
    proposed_by: str


class CanonicalResolver:
    """Service for resolving entities to canonical identities.

    Supports:
    - Exact matching (same name + context = 0.95 confidence)
    - Fuzzy matching (Levenshtein distance < 2 = 0.75 confidence)
    - Context matching (same cases/courts + similar names = 0.55 confidence)
    - Manual linking (admin explicit = 1.0 confidence)
    """

    # Confidence thresholds
    EXACT_MATCH_THRESHOLD = 0.95
    FUZZY_MATCH_THRESHOLD = 0.75
    CONTEXT_MATCH_THRESHOLD = 0.55
    MINIMUM_MATCH_THRESHOLD = 0.50

    def __init__(self, db: Session):
        self.db = db

    def resolve_judge(
        self,
        name: str,
        court_id: int | None = None,
        external_id: str | None = None,
    ) -> MatchResult:
        """Resolve a judge name to a canonical entity.

        Args:
            name: Judge name to resolve
            court_id: Optional court ID for context
            external_id: Optional external ID (e.g., CourtListener judge ID)

        Returns:
            MatchResult with canonical entity ID and confidence
        """
        # First, try exact match by external ID
        if external_id:
            entity = (
                self.db.query(CanonicalEntity)
                .filter(
                    CanonicalEntity.entity_type == "judge",
                    CanonicalEntity.canonical_id_external == external_id,
                    CanonicalEntity.status == "active",
                )
                .first()
            )
            if entity:
                return MatchResult(
                    canonical_entity_id=entity.id,
                    confidence=1.0,
                    match_reason="external_id",
                )

        # Try exact name match within same court context
        normalized_name = self._normalize_name(name)
        exact_match = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == "judge",
                func.lower(CanonicalEntity.canonical_name) == normalized_name,
                CanonicalEntity.status == "active",
            )
            .first()
        )

        if exact_match:
            # Verify with court context if provided
            confidence = self._EXACT_MATCH_THRESHOLD
            if court_id:
                # Check if this judge is already linked to this court
                court_link = (
                    self.db.query(EntitySourceRecord)
                    .filter(
                        EntitySourceRecord.canonical_entity_id == exact_match.id,
                        EntitySourceRecord.source_table == "courts",
                        EntitySourceRecord.source_record_id == court_id,
                    )
                    .first()
                )
                if court_link:
                    confidence = 1.0

            return MatchResult(
                canonical_entity_id=exact_match.id,
                confidence=confidence,
                match_reason="exact_name",
            )

        # Try fuzzy matching
        fuzzy_match = self._fuzzy_match_entity("judge", name, court_id)
        if fuzzy_match:
            return fuzzy_match

        # No match found
        return MatchResult(
            canonical_entity_id=None,
            confidence=0.0,
            match_reason="no_match",
        )

    def resolve_court(
        self,
        name: str,
        jurisdiction: str | None = None,
        city: str | None = None,
    ) -> MatchResult:
        """Resolve a court name to a canonical entity."""
        normalized_name = self._normalize_name(name)

        # Try exact match with jurisdiction context
        query = self.db.query(CanonicalEntity).filter(
            CanonicalEntity.entity_type == "court",
            func.lower(CanonicalEntity.canonical_name) == normalized_name,
            CanonicalEntity.status == "active",
        )

        if jurisdiction:
            # Look for jurisdiction in notes or use additional context
            pass  # Simplified for now

        exact_match = query.first()
        if exact_match:
            return MatchResult(
                canonical_entity_id=exact_match.id,
                confidence=self._EXACT_MATCH_THRESHOLD,
                match_reason="exact_name",
            )

        # Try fuzzy matching
        return self._fuzzy_match_entity("court", name, context_id=None)

    def create_canonical_entity(
        self,
        entity_type: str,
        canonical_name: str,
        source_table: str,
        source_record_id: int,
        source_name: str,
        external_id: str | None = None,
        created_by: str = "auto_resolver",
        match_confidence: float = 1.0,
    ) -> CanonicalEntity:
        """Create a new canonical entity and link it to a source record.

        Args:
            entity_type: Type of entity (judge, court, case, etc.)
            canonical_name: Normalized canonical name
            source_table: Source table name
            source_record_id: ID in source table
            source_name: Name of the source (e.g., "courtlistener")
            external_id: Optional external canonical ID
            created_by: Creator identifier
            match_confidence: Confidence in this canonical identity

        Returns:
            Created CanonicalEntity
        """
        # Create canonical entity
        entity = CanonicalEntity(
            entity_type=entity_type,
            canonical_name=canonical_name,
            canonical_id_external=external_id,
            merge_confidence=match_confidence,
            status="active",
            created_by=created_by,
        )
        self.db.add(entity)
        self.db.flush()  # Get the ID

        # Create source record link
        source_record = EntitySourceRecord(
            canonical_entity_id=entity.id,
            source_table=source_table,
            source_record_id=source_record_id,
            source_name=source_name,
            match_confidence=match_confidence,
            match_reason="initial_creation",
            linked_by=created_by,
        )
        self.db.add(source_record)
        self.db.commit()

        return entity

    def link_source_record(
        self,
        canonical_entity_id: int,
        source_table: str,
        source_record_id: int,
        source_name: str,
        match_confidence: float,
        match_reason: str,
        linked_by: str = "auto_resolver",
    ) -> EntitySourceRecord:
        """Link a source record to an existing canonical entity.

        Args:
            canonical_entity_id: ID of the canonical entity
            source_table: Source table name
            source_record_id: ID in source table
            source_name: Name of the source
            match_confidence: Confidence in the match (0.0-1.0)
            match_reason: Reason for the match
            linked_by: Who/what created the link

        Returns:
            Created EntitySourceRecord
        """
        # Check if link already exists
        existing = (
            self.db.query(EntitySourceRecord)
            .filter(
                EntitySourceRecord.canonical_entity_id == canonical_entity_id,
                EntitySourceRecord.source_table == source_table,
                EntitySourceRecord.source_record_id == source_record_id,
                EntitySourceRecord.source_name == source_name,
            )
            .first()
        )

        if existing:
            # Update confidence if higher
            if match_confidence > existing.match_confidence:
                existing.match_confidence = match_confidence
                existing.match_reason = match_reason
                self.db.commit()
            return existing

        # Create new link
        source_record = EntitySourceRecord(
            canonical_entity_id=canonical_entity_id,
            source_table=source_table,
            source_record_id=source_record_id,
            source_name=source_name,
            match_confidence=match_confidence,
            match_reason=match_reason,
            linked_by=linked_by,
        )
        self.db.add(source_record)
        self.db.commit()

        # Update last_verified_at on canonical entity
        entity = (
            self.db.query(CanonicalEntity)
            .filter(CanonicalEntity.id == canonical_entity_id)
            .first()
        )
        if entity:
            entity.last_verified_at = datetime.now(timezone.utc)
            self.db.commit()

        return source_record

    def find_duplicates(
        self,
        entity_type: str,
        threshold: float = 0.85,
    ) -> list[DuplicateGroup]:
        """Find potential duplicate entities based on name similarity.

        Args:
            entity_type: Type of entity to check
            threshold: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of DuplicateGroup with potential duplicates
        """
        # Get all active entities of this type
        entities = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.status == "active",
            )
            .all()
        )

        duplicate_groups: list[DuplicateGroup] = []
        checked_pairs: set[tuple[int, int]] = set()

        for i, entity1 in enumerate(entities):
            group_entities = [entity1]

            for entity2 in entities[i + 1 :]:
                # Create sorted pair to avoid duplicates
                pair = tuple(sorted([entity1.id, entity2.id]))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Calculate similarity
                similarity = difflib.SequenceMatcher(
                    None,
                    self._normalize_name(entity1.canonical_name),
                    self._normalize_name(entity2.canonical_name),
                ).ratio()

                if similarity >= threshold:
                    group_entities.append(entity2)

            if len(group_entities) > 1:
                duplicate_groups.append(
                    DuplicateGroup(
                        entities=group_entities,
                        similarity=max(
                            difflib.SequenceMatcher(
                                None,
                                self._normalize_name(e1.canonical_name),
                                self._normalize_name(e2.canonical_name),
                            ).ratio()
                            for e1 in group_entities
                            for e2 in group_entities
                            if e1.id != e2.id
                        ),
                    )
                )

        return duplicate_groups

    def propose_merge(
        self,
        entity_ids: list[int],
        target_canonical_id: int,
        reason: str,
        proposed_by: str,
    ) -> MergeProposal:
        """Propose merging multiple entities into one canonical identity.

        Args:
            entity_ids: IDs of entities to merge
            target_canonical_id: ID of the target canonical entity
            reason: Reason for the merge
            proposed_by: Who proposed the merge

        Returns:
            MergeProposal
        """
        # Calculate average confidence
        entities = (
            self.db.query(CanonicalEntity)
            .filter(CanonicalEntity.id.in_(entity_ids))
            .all()
        )

        avg_confidence = (
            sum(e.merge_confidence for e in entities) / len(entities)
            if entities
            else 0.0
        )

        return MergeProposal(
            entity_ids=entity_ids,
            target_canonical_id=target_canonical_id,
            confidence=avg_confidence,
            reason=reason,
            proposed_at=datetime.now(timezone.utc),
            proposed_by=proposed_by,
        )

    def apply_merge(
        self,
        proposal: MergeProposal,
        approved_by: str,
    ) -> CanonicalEntity:
        """Apply a merge proposal.

        Args:
            proposal: MergeProposal to apply
            approved_by: Admin who approved the merge

        Returns:
            The target CanonicalEntity after merge
        """
        target = (
            self.db.query(CanonicalEntity)
            .filter(CanonicalEntity.id == proposal.target_canonical_id)
            .first()
        )

        if not target:
            raise ValueError(f"Target entity {proposal.target_canonical_id} not found")

        # Update other entities to point to target
        for entity_id in proposal.entity_ids:
            if entity_id == proposal.target_canonical_id:
                continue

            entity = (
                self.db.query(CanonicalEntity)
                .filter(CanonicalEntity.id == entity_id)
                .first()
            )

            if entity:
                entity.status = "merged_into"
                entity.merged_into_id = proposal.target_canonical_id

                # Update source records to point to target
                self.db.query(EntitySourceRecord).filter(
                    EntitySourceRecord.canonical_entity_id == entity_id
                ).update({"canonical_entity_id": proposal.target_canonical_id})

        # Update target confidence
        target.merge_confidence = max(target.merge_confidence, proposal.confidence)
        target.notes = (
            f"Merged entities: {proposal.entity_ids}. Reason: {proposal.reason}"
        )

        self.db.commit()
        return target

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison."""
        return name.lower().strip().replace(",", "").replace(".", "")

    def _fuzzy_match_entity(
        self,
        entity_type: str,
        name: str,
        context_id: int | None = None,
    ) -> MatchResult | None:
        """Attempt fuzzy matching for an entity."""
        normalized_name = self._normalize_name(name)

        # Get candidates
        candidates = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.status == "active",
            )
            .all()
        )

        best_match: CanonicalEntity | None = None
        best_ratio = 0.0

        for candidate in candidates:
            ratio = difflib.SequenceMatcher(
                None,
                normalized_name,
                self._normalize_name(candidate.canonical_name),
            ).ratio()

            if ratio > best_ratio and ratio >= 0.85:
                best_ratio = ratio
                best_match = candidate

        if best_match:
            confidence = self._FUZZY_MATCH_THRESHOLD
            if best_ratio > 0.95:
                confidence = 0.90

            return MatchResult(
                canonical_entity_id=best_match.id,
                confidence=confidence,
                match_reason=f"fuzzy_match_{int(best_ratio * 100)}",
            )

        return None


@dataclass
class DuplicateGroup:
    """Group of potentially duplicate entities."""

    entities: list[CanonicalEntity]
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_ids": [e.id for e in self.entities],
            "entity_names": [e.canonical_name for e in self.entities],
            "similarity": self.similarity,
        }
