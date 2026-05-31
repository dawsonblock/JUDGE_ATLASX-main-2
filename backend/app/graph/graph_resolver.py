"""High-level graph-aware entity resolver.

Supersedes ``services/canonical_resolver.py`` as the authoritative entity
resolution layer.  The services module becomes a thin shim after Phase A
tests pass.

Resolution strategy (deterministic, no LLM):
1. External-ID lookup  → confidence 1.0
2. Exact canonical-ID (SHA-256) lookup → confidence 0.95
3. Exact normalised-name lookup → confidence 0.90
4. Fuzzy name scan (difflib) → confidence 0.70–0.89
5. Miss → is_new=True on get_or_create

No LLM calls.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.graph.canonical_ids import (
    generate_canonical_id,
    normalize_entity_name,
    CanonicalIdError,
)
from app.graph.confidence import weighted_confidence
from app.graph.entity_registry import get_registry
from app.graph.graph_merge import resolve_merge_chain

_FUZZY_THRESHOLD = 0.75
_EXACT_CONFIDENCE = 0.90
_FUZZY_MIN_SCORE = 0.70


@dataclass
class ResolveResult:
    """Result of an entity resolution attempt."""

    canonical_entity_id: int | None
    confidence: float
    match_reason: str
    is_new: bool = False


class GraphResolver:
    """Graph-aware canonical entity resolver.

    Args:
        db: SQLAlchemy session.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._registry = get_registry()

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def resolve(
        self,
        entity_type: str,
        name: str,
        external_id: str | None = None,
        context_ids: list[int] | None = None,
    ) -> ResolveResult:
        """Resolve an entity to an existing canonical ID (never creates).

        Args:
            entity_type:  Entity type string (e.g. ``"judge"``).
            name:         Raw display name.
            external_id:  Optional external identifier (CourtListener ID etc).
            context_ids:  Optional list of related entity IDs to narrow search.

        Returns:
            ResolveResult — ``canonical_entity_id`` is None on miss.
        """
        # 1. External-ID lookup
        if external_id:
            result = self._lookup_external(entity_type, external_id)
            if result is not None:
                return result

        # 2. Canonical-ID (SHA-256) lookup
        try:
            cid = generate_canonical_id(entity_type, name)
            result = self._lookup_canonical_id(entity_type, cid)
            if result is not None:
                return result
        except CanonicalIdError:
            pass

        # 3. Exact normalised-name lookup
        result = self._lookup_exact_name(entity_type, name)
        if result is not None:
            return result

        # 4. Fuzzy scan (restricted to same entity_type)
        result = self._lookup_fuzzy(entity_type, name)
        if result is not None:
            return result

        return ResolveResult(
            canonical_entity_id=None,
            confidence=0.0,
            match_reason="no_match",
        )

    def get_or_create(
        self,
        entity_type: str,
        name: str,
        external_id: str | None = None,
    ) -> ResolveResult:
        """Resolve entity or create a new canonical record if not found.

        Args:
            entity_type: Entity type string.
            name:        Raw display name.
            external_id: Optional external identifier.

        Returns:
            ResolveResult — ``is_new=True`` if a new row was inserted.
        """
        from app.models.entities import CanonicalEntity  # lazy

        result = self.resolve(entity_type, name, external_id=external_id)
        if result.canonical_entity_id is not None:
            return result

        # Create new canonical entity
        try:
            canonical_id_ext = (
                generate_canonical_id(entity_type, name)
                if not external_id
                else external_id
            )
        except CanonicalIdError:
            canonical_id_ext = None

        new_entity = CanonicalEntity(
            entity_type=entity_type,
            canonical_name=name,
            canonical_id_external=canonical_id_ext,
            merge_confidence=1.0,
            confidence_score=1.0,
            status="active",
            created_by="graph_resolver",
        )
        self.db.add(new_entity)
        self.db.flush()

        return ResolveResult(
            canonical_entity_id=new_entity.id,
            confidence=1.0,
            match_reason="created",
            is_new=True,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _lookup_external(
        self, entity_type: str, external_id: str
    ) -> ResolveResult | None:
        from app.models.entities import CanonicalEntity

        row = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.canonical_id_external == external_id,
                CanonicalEntity.status == "active",
            )
            .first()
        )
        if row is None:
            return None
        live_id = resolve_merge_chain(self.db, row.id)
        return ResolveResult(
            canonical_entity_id=live_id,
            confidence=1.0,
            match_reason="external_id_match",
        )

    def _lookup_canonical_id(
        self, entity_type: str, canonical_id_str: str
    ) -> ResolveResult | None:
        from app.models.entities import CanonicalEntity

        row = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.canonical_id_external == canonical_id_str,
                CanonicalEntity.status == "active",
            )
            .first()
        )
        if row is None:
            return None
        live_id = resolve_merge_chain(self.db, row.id)
        return ResolveResult(
            canonical_entity_id=live_id,
            confidence=0.95,
            match_reason="canonical_id_match",
        )

    def _lookup_exact_name(self, entity_type: str, name: str) -> ResolveResult | None:
        from app.models.entities import CanonicalEntity

        norm = normalize_entity_name(name)
        rows = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.status == "active",
            )
            .all()
        )
        for row in rows:
            if normalize_entity_name(row.canonical_name) == norm:
                live_id = resolve_merge_chain(self.db, row.id)
                return ResolveResult(
                    canonical_entity_id=live_id,
                    confidence=_EXACT_CONFIDENCE,
                    match_reason="exact_name_match",
                )
        return None

    def _lookup_fuzzy(self, entity_type: str, name: str) -> ResolveResult | None:
        from app.models.entities import CanonicalEntity

        norm = normalize_entity_name(name)
        rows = (
            self.db.query(CanonicalEntity)
            .filter(
                CanonicalEntity.entity_type == entity_type,
                CanonicalEntity.status == "active",
            )
            .all()
        )

        best_score = _FUZZY_THRESHOLD
        best_row = None
        for row in rows:
            score = difflib.SequenceMatcher(
                None, norm, normalize_entity_name(row.canonical_name)
            ).ratio()
            if score > best_score:
                best_score = score
                best_row = row

        if best_row is None:
            return None

        live_id = resolve_merge_chain(self.db, best_row.id)
        confidence = weighted_confidence(
            [_FUZZY_MIN_SCORE, best_score], weights=[0.4, 0.6]
        )
        return ResolveResult(
            canonical_entity_id=live_id,
            confidence=confidence,
            match_reason=f"fuzzy_name_match({best_score:.2f})",
        )
