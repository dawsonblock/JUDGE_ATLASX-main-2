"""Deterministic checksumming for memory claims and state.

Enables reproducible rebuilds and drift detection.
"""

import hashlib
import json
from typing import Any


def stable_json_hash(payload: Any) -> str:
    """Generate deterministic SHA256 of JSON data.
    
    Uses stable JSON serialization (sorted keys, no spaces) to ensure
    identical payloads always produce identical hashes.
    
    Args:
        payload: Any JSON-serializable object
        
    Returns:
        SHA256 hex digest
    """
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def claim_key(payload: dict) -> str:
    """Generate deterministic key for a memory claim.
    
    Key is based on claim content (not ID), enabling idempotent updates
    and deduplication across rebuilds.
    
    Args:
        payload: Claim dict with claim_type, subject_type, subject_id, etc.
        
    Returns:
        SHA256 hex digest as stable claim key
    """
    normalized = {
        "claim_type": payload["claim_type"],
        "subject_type": payload["subject_type"],
        "subject_id": str(payload["subject_id"]),
        "predicate": payload["predicate"],
        "object_type": payload.get("object_type"),
        "object_id": str(payload.get("object_id")) if payload.get("object_id") is not None else None,
        "normalized_text": payload["normalized_text"].strip().lower(),
    }
    return stable_json_hash(normalized)


def evidence_checksum(items: list[dict]) -> str:
    """Generate checksum across multiple evidence items.
    
    Sorts items before hashing to ensure consistent checksums regardless
    of input order.
    
    Args:
        items: List of evidence item dicts
        
    Returns:
        SHA256 hex digest across all items
    """
    sorted_items = sorted(
        items,
        key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"), default=str)
    )
    return stable_json_hash(sorted_items)


def entity_summary_checksum(claims: list[dict]) -> str:
    """Generate checksum for entity summary from claims.
    
    Used to detect when entity state has become stale.
    
    Args:
        claims: List of active MemoryClaim dicts for entity
        
    Returns:
        SHA256 hex digest
    """
    claim_keys = sorted([claim["claim_key"] for claim in claims])
    return stable_json_hash({
        "claim_keys": claim_keys,
        "claim_count": len(claims),
    })


def state_checksum(state: dict) -> str:
    """Generate checksum for memory state object.
    
    Args:
        state: State dict (entity summary, relationship, etc.)
        
    Returns:
        SHA256 hex digest
    """
    return stable_json_hash(state)
