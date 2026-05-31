"""Memory rebuild orchestration.

Drives a MemoryRebuildRun: iterates canonical entities, extracts claims
via extract_claims.py, upserts MemoryClaim + MemoryEvidenceLink rows,
and updates MemoryEntityState checksums.

Does NOT import from map_record, graph edge, or public event tables.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.memory import entity_summary_checksum
from app.memory.extract_claims import extract_claims
from app.memory.invalidation import invalidate_claim
from app.memory.memory_graph_bridge import sync_claims_to_graph
from app.models.entities import (
    CanonicalEntity,
    EntityEvidenceLink,
    MemoryClaim,
    MemoryEntityState,
    MemoryEvidenceLink,
    MemoryRebuildRun,
    SourceSnapshot,
)

# Claims with these reasons are never overwritten by stale-rebuild invalidation.
_HARD_REASONS: frozenset[str] = frozenset(
    {"manual_reject", "source_rejected", "privacy_violation"}
)


def _get_latest_snapshot_for_entity(
    db: Session,
    entity_id: int,
) -> SourceSnapshot | None:
    """Return the most recent SourceSnapshot linked to this entity.

    Joins through EntityEvidenceLink to scope the query to snapshots
    that actually contain evidence for this entity. Returns None if no
    entity-scoped snapshots exist rather than falling back to an
    unrelated global snapshot.
    """
    return (
        db.query(SourceSnapshot)
        .join(EntityEvidenceLink, EntityEvidenceLink.snapshot_id == SourceSnapshot.id)
        .filter(EntityEvidenceLink.entity_id == entity_id)
        .order_by(SourceSnapshot.fetched_at.desc())
        .first()
    )


def _get_all_snapshots_for_entity(
    db: Session,
    entity_id: int,
) -> list[SourceSnapshot]:
    """Return all SourceSnapshots linked to this entity, oldest-first.

    Claims from all snapshots are accumulated so that evidence from earlier
    fetches is not lost when a newer snapshot is processed.
    """
    return (
        db.query(SourceSnapshot)
        .join(EntityEvidenceLink, EntityEvidenceLink.snapshot_id == SourceSnapshot.id)
        .filter(EntityEvidenceLink.entity_id == entity_id)
        .order_by(SourceSnapshot.fetched_at.asc())
        .all()
    )


def _get_current_snapshots_for_entity(
    db: Session,
    entity_id: int,
) -> list[SourceSnapshot]:
    """Return the latest SourceSnapshot per source_key for this entity.

    Prevents stale claims from old fetches from persisting across rebuild runs
    by selecting only the most-recently-fetched snapshot for each distinct
    source_key rather than accumulating all historical snapshots.
    """
    # Use coalesce(source_key, source_url) as the grouping key so that
    # snapshots with a NULL source_key are grouped by their URL rather than
    # all collapsing into a single NULL bucket.
    _group_key = sqlfunc.coalesce(SourceSnapshot.source_key, SourceSnapshot.source_url)
    subq = (
        db.query(
            _group_key.label("group_key"),
            sqlfunc.max(SourceSnapshot.fetched_at).label("max_fetched_at"),
        )
        .join(EntityEvidenceLink, EntityEvidenceLink.snapshot_id == SourceSnapshot.id)
        .filter(EntityEvidenceLink.entity_id == entity_id)
        .group_by(_group_key)
        .subquery()
    )
    return (
        db.query(SourceSnapshot)
        .join(EntityEvidenceLink, EntityEvidenceLink.snapshot_id == SourceSnapshot.id)
        .filter(EntityEvidenceLink.entity_id == entity_id)
        .join(
            subq,
            (
                sqlfunc.coalesce(SourceSnapshot.source_key, SourceSnapshot.source_url)
                == subq.c.group_key
            )
            & (SourceSnapshot.fetched_at == subq.c.max_fetched_at),
        )
        .all()
    )


def _upsert_claims(
    db: Session,
    entity_id: int,
    extracted: list[dict],
    snapshot: SourceSnapshot,
    run_id: int | None = None,
) -> tuple[int, int, set[str]]:
    """Insert new claims, skip existing (by claim_key).

    Accepts either fully-formed claim dicts (with claim_key and entity_id) or
    minimal dicts (claim_type + claim_value + confidence); missing fields are
    auto-generated so that both extract_claims output and bare test fixtures work.

    Returns:
        (created, skipped, produced_keys) where produced_keys contains every
        claim_key visited (new and existing), used by run_rebuild() to detect
        stale claims.
    """
    created = 0
    skipped = 0
    produced_keys: set[str] = set()
    for c in extracted:
        # Auto-fill entity_id and claim_key when not provided (e.g. bare test fixtures).
        eid = c.get("entity_id") or entity_id
        if "claim_key" in c:
            key = c["claim_key"]
        else:
            raw = f"{eid}:{c['claim_type']}:{c['claim_value']}"
            key = hashlib.sha256(raw.encode()).hexdigest()
        existing = db.query(MemoryClaim).filter(MemoryClaim.claim_key == key).first()
        if existing is not None:
            # Accumulate new evidence for the existing claim instead of silently skipping.
            existing_link = (
                db.query(MemoryEvidenceLink)
                .filter(
                    MemoryEvidenceLink.claim_id == existing.id,
                    MemoryEvidenceLink.snapshot_id == snapshot.id,
                )
                .first()
            )
            if existing_link is None:
                ev_span: str | None = None
                if c.get("span_start") is not None and c.get("span_end") is not None:
                    src = snapshot.extracted_text or ""
                    ev_span = src[c["span_start"] : c["span_end"]]
                db.add(
                    MemoryEvidenceLink(
                        claim_id=existing.id,
                        snapshot_id=snapshot.id,
                        evidence_checksum=snapshot.content_hash or "",
                        span_start=c.get("span_start"),
                        span_end=c.get("span_end"),
                        span_text=ev_span,
                    )
                )
                db.flush()
            # Refresh last_seen_at and reactivate unless the claim was hard-rejected.
            if existing.invalidation_reason not in _HARD_REASONS:
                now = datetime.now(timezone.utc)
                existing.last_seen_at = now
                existing.status = "active"
                existing.is_active = True
            produced_keys.add(key)
            skipped += 1
            continue

        claim = MemoryClaim(
            claim_key=key,
            claim_type=c["claim_type"],
            entity_id=eid,
            claim_value=c["claim_value"],
            claim_value_json=c.get("claim_value_json"),
            confidence=c.get("confidence", 0.0),
            source_snapshot_id=snapshot.id,
            is_active=True,
        )
        db.add(claim)
        db.flush()  # populate claim.id

        # Optionally store a semantic embedding for this claim.
        try:
            from app.services.embeddings import encode as _encode  # noqa: PLC0415

            vec = _encode(c["claim_value"])
            if vec is not None:
                claim.claim_embedding = vec
        except Exception:  # pragma: no cover — embeddings are optional
            pass

        span_text: str | None = None
        if c.get("span_start") is not None and c.get("span_end") is not None:
            src = snapshot.extracted_text or ""
            span_text = src[c["span_start"] : c["span_end"]]

        db.add(
            MemoryEvidenceLink(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                evidence_checksum=snapshot.content_hash or "",
                span_start=c.get("span_start"),
                span_end=c.get("span_end"),
                span_text=span_text,
            )
        )
        db.flush()
        produced_keys.add(key)
        created += 1
    return created, skipped, produced_keys


def _rebuild_entity_state(
    entity: CanonicalEntity,
    rebuild_run: MemoryRebuildRun,
    db: Session,
) -> bool:
    """Compute and upsert MemoryEntityState for *entity*.

    Returns True if the state was created or updated, False if unchanged.
    """
    active_claims = (
        db.query(MemoryClaim)
        .filter(MemoryClaim.entity_id == entity.id, MemoryClaim.is_active.is_(True))
        .all()
    )
    claims_as_dicts = [
        {"claim_key": c.claim_key, "claim_type": c.claim_type} for c in active_claims
    ]
    checksum = entity_summary_checksum(claims_as_dicts)

    state = (
        db.query(MemoryEntityState)
        .filter(MemoryEntityState.entity_id == entity.id)
        .first()
    )

    aliases: list[str] = []
    roles: list[str] = []
    for claim in active_claims:
        if claim.claim_type == "name_mention":
            val = (claim.claim_value_json or {}).get("alias") or claim.claim_value
            if val and val not in aliases:
                aliases.append(val)
        elif claim.claim_type == "role":
            role = (claim.claim_value_json or {}).get("role") or claim.claim_value
            if role and role not in roles:
                roles.append(role)

    now = datetime.now(timezone.utc)

    if state is None:
        db.add(
            MemoryEntityState(
                entity_id=entity.id,
                state_checksum=checksum,
                display_name=entity.canonical_name,
                aliases=aliases or None,
                roles=roles or None,
                jurisdictions=None,
                last_rebuild_run_id=rebuild_run.id,
                rebuilt_at=now,
                active_claim_count=len(active_claims),
            )
        )
        return True

    if state.state_checksum == checksum:
        return False  # nothing changed

    state.state_checksum = checksum
    state.display_name = entity.canonical_name
    state.aliases = aliases or None
    state.roles = roles or None
    state.last_rebuild_run_id = rebuild_run.id
    state.rebuilt_at = now
    state.active_claim_count = len(active_claims)
    return True


def run_rebuild(
    scope: str,
    db: Session,
    entity_id: int | None = None,
) -> MemoryRebuildRun:
    """Orchestrate a memory rebuild run.

    Args:
        scope:     "full" rebuilds all active entities; "entity" scopes to one.
        db:        SQLAlchemy session (caller is responsible for commit/rollback).
        entity_id: Required when scope="entity".

    Returns:
        The completed (or failed) MemoryRebuildRun.
    """
    if scope not in {"full", "entity"}:
        raise ValueError(f"Unknown rebuild scope: {scope!r}")
    if scope == "entity" and entity_id is None:
        raise ValueError("entity_id is required for scope='entity'")

    # Resolve entities before creating the run record — ValueError from here propagates to caller
    if scope == "entity":
        entity = db.get(CanonicalEntity, entity_id)
        if entity is None:
            raise ValueError(f"CanonicalEntity {entity_id} does not exist")
        pre_entities: list[CanonicalEntity] | None = [entity]
    else:
        pre_entities = None  # fetched inside try so errors are captured on the run

    run = MemoryRebuildRun(
        rebuild_scope=scope,
        scope_entity_id=entity_id,
        status="running",
        started_at=datetime.now(timezone.utc),
        entities_processed=0,
        claims_created=0,
        claims_invalidated=0,
        states_updated=0,
    )
    db.add(run)
    db.flush()

    try:
        entities: list[CanonicalEntity] = (
            pre_entities
            if pre_entities is not None
            else (
                db.query(CanonicalEntity)
                .filter(CanonicalEntity.status == "active")
                .all()
            )
        )
        for entity in entities:
            run.entities_processed += 1
            snapshots = _get_current_snapshots_for_entity(db, entity.id)
            if not snapshots:
                continue

            entity_produced_keys: set[str] = set()
            for snapshot in snapshots:
                extracted = extract_claims(snapshot, entity, db)
                created, _, snapshot_keys = _upsert_claims(
                    db, entity.id, extracted, snapshot, run.id
                )
                run.claims_created += created
                entity_produced_keys |= snapshot_keys

            # Invalidate claims whose key is no longer produced by any current snapshot.
            active_claims = (
                db.query(MemoryClaim)
                .filter(
                    MemoryClaim.entity_id == entity.id,
                    MemoryClaim.is_active.is_(True),
                )
                .all()
            )
            for claim in active_claims:
                if (
                    claim.claim_key not in entity_produced_keys
                    and claim.invalidation_reason not in _HARD_REASONS
                ):
                    invalidate_claim(claim.id, "stale_rebuild", db, run.id)
                    run.claims_invalidated += 1

            if _rebuild_entity_state(entity, run, db):
                run.states_updated += 1

            # Propagate active claims to the entity graph.
            still_active = [
                c
                for c in active_claims
                if c.claim_key in entity_produced_keys and c.is_active
            ]
            sync_claims_to_graph(entity.id, still_active, db)

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)

    except Exception as exc:
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.error_message = str(exc)

    return run
