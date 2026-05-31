"""Deterministic claim extraction from source snapshots.

Extracts structured claims about canonical entities from snapshot text.
Claims are returned as dicts; persistence is handled by rebuild.py.

Does NOT import from map_record, graph edge, or public event tables.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.memory import claim_key
from app.models.entities import CanonicalEntity, SourceSnapshot


def _build_claim(
    entity: CanonicalEntity,
    claim_type: str,
    predicate: str,
    normalized_text: str,
    confidence: float,
    span_start: int | None = None,
    span_end: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "claim_type": claim_type,
        "subject_type": entity.entity_type,
        "subject_id": entity.id,
        "predicate": predicate,
        "object_type": None,
        "object_id": None,
        "normalized_text": normalized_text,
    }
    key = claim_key(payload)
    return {
        "claim_key": key,
        "claim_type": claim_type,
        "entity_id": entity.id,
        "claim_value": normalized_text,
        "claim_value_json": extra,
        "confidence": confidence,
        "span_start": span_start,
        "span_end": span_end,
    }


_ROLE_PATTERNS: dict[str, list[str]] = {
    "district judge": [
        "district judge",
        "u.s. district judge",
        "federal district judge",
    ],
    "circuit judge": ["circuit judge", "appeals court judge", "court of appeals"],
    "magistrate judge": ["magistrate judge", "magistrate"],
    "bankruptcy judge": ["bankruptcy judge"],
    "chief judge": ["chief judge"],
    "senior judge": ["senior judge"],
}

# Regex patterns for structured event claim extraction.
# Each tuple: (compiled pattern, claim_type, predicate, value_fn)
# value_fn receives the match object and returns (normalized_value, extra_dict).

_BAIL_PATTERN = re.compile(
    r"\b(bail|bond|detention|release)\s+(was\s+)?(granted|denied|revoked|set|posted|ordered)\b"
    r"|\b(ordered\s+)(detained|released|remanded)\b"
    r"|\b(pre[- ]?trial\s+)(release|detention)\b",
    re.IGNORECASE,
)

_SENTENCE_PATTERN = re.compile(
    r"\bsentenced?\s+to\s+(?P<length>[\d]+(?:\.\d+)?\s*(?:year|month|day|life)[s]?(?:\s+(?:and\s+)?[\d]+\s*(?:year|month|day)[s]?)?)\b"
    r"|\b(?P<life>life\s+(?:in\s+prison|imprisonment|sentence))\b"
    r"|\b(?P<probation>[\d]+\s*(?:year|month)[s]?\s+(?:of\s+)?probation)\b",
    re.IGNORECASE,
)

_COURT_APPEARANCE_PATTERN = re.compile(
    r"\b(?:appeared?|appearing|scheduled|set\s+for\s+(?:hearing|trial|arraignment)|"
    r"arraigned?|indicted?|preliminary\s+hearing|status\s+conference|"
    r"sentencing\s+hearing|bond\s+hearing|detention\s+hearing)\b",
    re.IGNORECASE,
)

_CHARGE_PATTERN = re.compile(
    r"\bcharged?\s+with\s+(?P<charge>[^.;]{3,80}?)(?:\.|;|,\s+(?:a|an)\s+\w+|$)"
    r"|\bcounts?\s+of\s+(?P<charge2>[^.;]{3,80}?)(?:\.|;|,|$)"
    r"|\bindicted?\s+(?:on\s+)?(?:charges?\s+of\s+)?(?P<charge3>[^.;]{3,80}?)(?:\.|;|,|$)",
    re.IGNORECASE,
)

_DISPOSITION_PATTERN = re.compile(
    r"\b(?P<disp>convicted|acquitted|found\s+(?:guilty|not\s+guilty)|pleaded?\s+(?:guilty|no\s+contest|nolo\s+contendere)|"
    r"dismissed|case\s+dismissed|charges?\s+dropped|pled\s+guilty|entered\s+(?:a\s+)?guilty\s+plea)\b",
    re.IGNORECASE,
)


def extract_claims(
    snapshot: SourceSnapshot,
    entity: CanonicalEntity,
    db: Session,  # noqa: ARG001 — reserved for future enrichment lookups
) -> list[dict[str, Any]]:
    """Extract structured claims about *entity* from *snapshot*.

    Returns a list of claim dicts without persisting anything.
    Each dict contains: claim_key, claim_type, entity_id, claim_value,
    claim_value_json, confidence, span_start, span_end.
    """
    text = snapshot.extracted_text or snapshot.raw_content or ""
    claims: list[dict[str, Any]] = []

    # Entity-type claim is always emitted when there is any text.
    if text:
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="entity_type",
                predicate="is_type",
                normalized_text=entity.entity_type,
                confidence=1.0,
                extra={"entity_type": entity.entity_type},
            )
        )

    # Canonical-name mention claim when entity name appears in text.
    name_pattern = re.compile(re.escape(entity.canonical_name), re.IGNORECASE)
    first_match = name_pattern.search(text)
    if first_match:
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="name_mention",
                predicate="mentioned_in",
                normalized_text=entity.canonical_name.strip().lower(),
                confidence=0.95,
                span_start=first_match.start(),
                span_end=first_match.end(),
            )
        )

    # Role keyword extraction — scoped to ±300-char window around entity mention.
    text_lower = text.lower()
    if first_match:
        WINDOW = 300
        w_start = max(0, first_match.start() - WINDOW)
        w_end = min(len(text), first_match.end() + WINDOW)
        window_lower = text_lower[w_start:w_end]
    else:
        w_start = 0
        window_lower = text_lower
    for role, patterns in _ROLE_PATTERNS.items():
        for pat in patterns:
            idx = window_lower.find(pat)
            if idx != -1:
                abs_start = w_start + idx
                claims.append(
                    _build_claim(
                        entity=entity,
                        claim_type="role",
                        predicate="has_role",
                        normalized_text=role,
                        confidence=0.8,
                        span_start=abs_start,
                        span_end=abs_start + len(pat),
                        extra={"role": role, "matched_pattern": pat},
                    )
                )
                break  # one match per role type

    # --- bail_decision ---
    search_text = window_lower if first_match else text_lower
    m = _BAIL_PATTERN.search(search_text)
    if m:
        abs_start = w_start + m.start() if first_match else m.start()
        # Determine outcome from which group matched
        grps = m.groups()
        if any(g and "grant" in g.lower() for g in grps if g):
            outcome = "granted"
        elif any(
            g
            and ("deni" in g.lower() or "detain" in g.lower() or "remand" in g.lower())
            for g in grps
            if g
        ):
            outcome = "denied"
        elif any(g and "revok" in g.lower() for g in grps if g):
            outcome = "revoked"
        else:
            outcome = m.group().strip().lower()
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="bail_decision",
                predicate="has_bail_decision",
                normalized_text=outcome,
                confidence=0.85,
                span_start=abs_start,
                span_end=abs_start + len(m.group()),
                extra={"outcome": outcome, "matched_text": m.group()},
            )
        )

    # --- sentence_length ---
    m = _SENTENCE_PATTERN.search(search_text)
    if m:
        abs_start = w_start + m.start() if first_match else m.start()
        length_text = (
            m.group("length") or m.group("life") or m.group("probation") or m.group()
        )
        length_text = length_text.strip()
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="sentence_length",
                predicate="sentenced_to",
                normalized_text=length_text.lower(),
                confidence=0.88,
                span_start=abs_start,
                span_end=abs_start + len(m.group()),
                extra={"length_text": length_text},
            )
        )

    # --- court_appearance ---
    m = _COURT_APPEARANCE_PATTERN.search(search_text)
    if m:
        abs_start = w_start + m.start() if first_match else m.start()
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="court_appearance",
                predicate="has_court_appearance",
                normalized_text=m.group().strip().lower(),
                confidence=0.75,
                span_start=abs_start,
                span_end=abs_start + len(m.group()),
                extra={"matched_text": m.group()},
            )
        )

    # --- charge_type ---
    m = _CHARGE_PATTERN.search(search_text)
    if m:
        abs_start = w_start + m.start() if first_match else m.start()
        raw_charge = (
            m.group("charge") or m.group("charge2") or m.group("charge3") or m.group()
        )
        raw_charge = raw_charge.strip()
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="charge_type",
                predicate="charged_with",
                normalized_text=raw_charge.lower(),
                confidence=0.82,
                span_start=abs_start,
                span_end=abs_start + len(m.group()),
                extra={"charge_text": raw_charge},
            )
        )

    # --- disposition ---
    m = _DISPOSITION_PATTERN.search(search_text)
    if m:
        abs_start = w_start + m.start() if first_match else m.start()
        raw = (m.group("disp") or m.group()).strip().lower()
        # normalise verbose phrases
        if "not guilty" in raw or "acquit" in raw:
            outcome = "acquitted"
        elif "guilty" in raw or "convict" in raw:
            outcome = "convicted"
        elif "dismiss" in raw or "dropped" in raw:
            outcome = "dismissed"
        elif "nolo" in raw or "no contest" in raw:
            outcome = "plea_no_contest"
        else:
            outcome = raw
        claims.append(
            _build_claim(
                entity=entity,
                claim_type="disposition",
                predicate="has_disposition",
                normalized_text=outcome,
                confidence=0.87,
                span_start=abs_start,
                span_end=abs_start + len(m.group()),
                extra={"outcome": outcome, "matched_text": m.group()},
            )
        )

    return claims
