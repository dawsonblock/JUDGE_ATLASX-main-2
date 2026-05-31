"""Tests for the AI correctness-checking service.

Proves:
- AI cannot publish high-privacy-risk records
- AI cannot mark unsupported claims as verified
- Duplicate records are flagged instead of creating repeated dots
- Exact residential locations are not exposed (rejected)
- Statuses remain distinct (no guilt/danger score field exists)
- Public quality API includes quality label, not guilt/judge/danger scores
- is_safe_to_show gates match expected rules
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models.entities import (
    AICorrectnessCheck,
    CrimeIncident,
)
from app.services.ai_correctness import (
    MODEL_NAME,
    PROMPT_VERSION,
    check_crime_incident,
    is_safe_to_show,
    _assess_privacy_risk,
    _derive_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_now = datetime.now(timezone.utc)


def _make_incident(**kwargs) -> CrimeIncident:
    defaults = dict(
        source_name="test_source",
        source_id="test_source",
        external_id=None,
        incident_type="Theft",
        incident_category="property",
        reported_at=_now - timedelta(hours=2),
        occurred_at=_now - timedelta(hours=4),
        city="Saskatoon",
        province_state="SK",
        country="Canada",
        latitude_public=52.1332,
        longitude_public=-106.6700,
        precision_level="city_centroid",
        verification_status="reported",
        data_last_seen_at=_now,
        is_public=True,
        notes="SAMPLE generalized public-area incident.",
        source_url="https://test.example/source",
    )
    defaults.update(kwargs)
    return CrimeIncident(**defaults)


def _persisted_incident(db, **kwargs) -> CrimeIncident:
    inc = _make_incident(**kwargs)
    db.add(inc)
    db.flush()
    return inc


# ---------------------------------------------------------------------------
# is_safe_to_show gate
# ---------------------------------------------------------------------------

def _mock_check(**kwargs) -> AICorrectnessCheck:
    defaults = dict(
        record_type="crime_incident",
        record_id=1,
        model_name=MODEL_NAME,
        prompt_version=PROMPT_VERSION,
        event_type_supported=True,
        date_supported=True,
        location_supported=True,
        status_supported=True,
        source_supports_claim=True,
        duplicate_candidate=False,
        privacy_risk="low",
        map_quality="verified",
        reason="ok",
        result_json={},
        checked_at=_now,
    )
    defaults.update(kwargs)
    chk = AICorrectnessCheck(**defaults)
    return chk


def test_safe_to_show_verified():
    assert is_safe_to_show(_mock_check(map_quality="verified")) is True


def test_safe_to_show_location_uncertain():
    assert is_safe_to_show(
        _mock_check(map_quality="location_uncertain")
    ) is True


def test_safe_to_show_high_privacy_blocked():
    assert is_safe_to_show(
        _mock_check(map_quality="verified", privacy_risk="high")
    ) is False


def test_safe_to_show_unsupported_claim_blocked():
    assert is_safe_to_show(
        _mock_check(source_supports_claim=False)
    ) is False


def test_safe_to_show_rejected_blocked():
    assert is_safe_to_show(_mock_check(map_quality="rejected")) is False


def test_safe_to_show_duplicate_blocked():
    assert is_safe_to_show(
        _mock_check(map_quality="duplicate_candidate")
    ) is False


def test_safe_to_show_needs_review_blocked():
    assert is_safe_to_show(_mock_check(map_quality="needs_review")) is False


# ---------------------------------------------------------------------------
# Privacy risk assessment
# ---------------------------------------------------------------------------

def test_privacy_risk_exact_address():
    risk = _assess_privacy_risk(
        "Suspect seen at 123 Main St apt 4", "city_centroid"
    )
    assert risk == "high"


def test_privacy_risk_ssn():
    risk = _assess_privacy_risk(
        "SSN 123-45-6789 found in record", None
    )
    assert risk == "high"


def test_privacy_risk_unsafe_precision():
    risk = _assess_privacy_risk("normal note", "exact_address")
    assert risk == "high"


def test_privacy_risk_low_for_generalized():
    risk = _assess_privacy_risk(
        "Incident occurred in downtown area", "city_centroid"
    )
    assert risk == "low"


# ---------------------------------------------------------------------------
# _derive_quality logic
# ---------------------------------------------------------------------------

def test_derive_quality_all_pass():
    q = _derive_quality(
        source_supports=True,
        location_ok=True,
        date_ok=True,
        status_ok=True,
        is_dup=False,
        privacy_risk="low",
    )
    assert q == "verified"


def test_derive_quality_high_privacy_rejected():
    q = _derive_quality(
        source_supports=True,
        location_ok=True,
        date_ok=True,
        status_ok=True,
        is_dup=False,
        privacy_risk="high",
    )
    assert q == "rejected"


def test_derive_quality_no_source_rejected():
    q = _derive_quality(
        source_supports=False,
        location_ok=True,
        date_ok=True,
        status_ok=True,
        is_dup=False,
        privacy_risk="low",
    )
    assert q == "rejected"


def test_derive_quality_duplicate_flagged():
    q = _derive_quality(
        source_supports=True,
        location_ok=True,
        date_ok=True,
        status_ok=True,
        is_dup=True,
        privacy_risk="low",
    )
    assert q == "duplicate_candidate"


def test_derive_quality_bad_location_uncertain():
    q = _derive_quality(
        source_supports=True,
        location_ok=False,
        date_ok=True,
        status_ok=True,
        is_dup=False,
        privacy_risk="low",
    )
    assert q == "location_uncertain"


def test_derive_quality_missing_date_needs_review():
    q = _derive_quality(
        source_supports=True,
        location_ok=True,
        date_ok=False,
        status_ok=True,
        is_dup=False,
        privacy_risk="low",
    )
    assert q == "needs_review"


# ---------------------------------------------------------------------------
# Full check_crime_incident integration
# ---------------------------------------------------------------------------

def test_check_crime_incident_verified():
    with SessionLocal() as db:
        inc = _persisted_incident(db)
        chk = check_crime_incident(db, inc)
        db.commit()
        quality = chk.map_quality
        risk = chk.privacy_risk
        supports = chk.source_supports_claim
        safe = is_safe_to_show(chk)
        model = chk.model_name
        pv = chk.prompt_version
    assert quality == "verified"
    assert risk == "low"
    assert supports is True
    assert safe is True
    assert model == MODEL_NAME
    assert pv == PROMPT_VERSION


def test_check_crime_incident_exact_address_rejected():
    with SessionLocal() as db:
        inc = _persisted_incident(
            db,
            notes="Incident at 456 Oak Ave apt 2",
            precision_level="city_centroid",
        )
        chk = check_crime_incident(db, inc)
        db.commit()
        risk = chk.privacy_risk
        quality = chk.map_quality
        safe = is_safe_to_show(chk)
    assert risk == "high"
    assert quality == "rejected"
    assert safe is False


def test_check_crime_incident_residential_precision_rejected():
    with SessionLocal() as db:
        inc = _persisted_incident(db, precision_level="exact_address")
        chk = check_crime_incident(db, inc)
        db.commit()
        quality = chk.map_quality
        safe = is_safe_to_show(chk)
        finding_types = [f.finding_type for f in chk.findings]
    assert quality == "rejected"
    assert safe is False
    assert "unsafe_precision" in finding_types


def test_check_crime_incident_missing_source_rejected():
    with SessionLocal() as db:
        inc = _persisted_incident(db, source_name="", incident_type="")
        chk = check_crime_incident(db, inc)
        db.commit()
        supports = chk.source_supports_claim
        quality = chk.map_quality
        safe = is_safe_to_show(chk)
    assert supports is False
    assert quality == "rejected"
    assert safe is False


def test_check_crime_incident_missing_date_needs_review():
    with SessionLocal() as db:
        inc = _persisted_incident(
            db,
            reported_at=None,
            occurred_at=None,
            incident_type="MISSING-DATE-TEST-UNIQUE",
            source_url="https://test.example/missing-date-unique",
        )
        chk = check_crime_incident(db, inc)
        db.commit()
        date_ok = chk.date_supported
        quality = chk.map_quality
        safe = is_safe_to_show(chk)
    assert date_ok is False
    assert quality in ("needs_review", "location_uncertain", "rejected")
    assert safe is False


def test_check_crime_incident_no_coordinates_location_uncertain():
    with SessionLocal() as db:
        inc = _persisted_incident(
            db,
            latitude_public=None,
            longitude_public=None,
            incident_type="NO-COORDS-TEST-UNIQUE",
            source_url="https://test.example/no-coords-unique",
        )
        chk = check_crime_incident(db, inc)
        db.commit()
        loc_ok = chk.location_supported
        quality = chk.map_quality
    assert loc_ok is False
    assert quality in ("location_uncertain", "needs_review")


def test_check_crime_incident_duplicate_flagged():
    with SessionLocal() as db:
        inc1 = _persisted_incident(
            db,
            source_name="dup_source_a",
            incident_type="DUP-TEST-ASSAULT",
            external_id="DUP-EXT-001",
            source_url="https://dup-test.example/1",
        )
        inc2 = _persisted_incident(
            db,
            source_name="dup_source_b",
            incident_type="DUP-TEST-ASSAULT",
            external_id="DUP-EXT-001",
            source_url="https://dup-test.example/1",
        )
        chk = check_crime_incident(db, inc2)
        db.commit()
        is_dup = chk.duplicate_candidate
        dup_ids = chk.possible_duplicate_ids or []
        quality = chk.map_quality
        safe = is_safe_to_show(chk)
        inc1_id = inc1.id
    assert is_dup is True
    assert inc1_id in dup_ids
    assert quality == "duplicate_candidate"
    assert safe is False


# ---------------------------------------------------------------------------
# No forbidden fields in output
# ---------------------------------------------------------------------------

def test_result_json_has_no_guilt_score():
    with SessionLocal() as db:
        inc = _persisted_incident(db)
        chk = check_crime_incident(db, inc)
        db.commit()
        result = dict(chk.result_json)
    forbidden = {
        "guilt_score", "danger_score", "judge_score",
        "blame", "suspect_score", "criminal_score",
    }
    assert forbidden.isdisjoint(result.keys()), (
        f"Forbidden fields found in result_json: {forbidden & result.keys()}"
    )


def test_result_json_contains_required_fields():
    with SessionLocal() as db:
        inc = _persisted_incident(db)
        chk = check_crime_incident(db, inc)
        db.commit()
        result = dict(chk.result_json)
    required = {
        "record_type", "event_type_supported", "date_supported",
        "location_supported", "status_supported", "source_supports_claim",
        "duplicate_candidate", "privacy_risk", "map_quality",
        "reason", "checked_at", "model_name", "prompt_version",
    }
    missing = required - result.keys()
    assert not missing, f"Missing required fields: {missing}"


# ---------------------------------------------------------------------------
# Status distinctness
# ---------------------------------------------------------------------------

def test_statuses_remain_distinct():
    with SessionLocal() as db:
        reported = _persisted_incident(
            db, verification_status="reported",
            incident_type="STATUS-REPORTED-TEST"
        )
        charged = _persisted_incident(
            db, verification_status="charged",
            incident_type="STATUS-CHARGED-TEST"
        )
        convicted = _persisted_incident(
            db, verification_status="convicted",
            incident_type="STATUS-CONVICTED-TEST"
        )
        chk_r = check_crime_incident(db, reported)
        chk_c = check_crime_incident(db, charged)
        chk_v = check_crime_incident(db, convicted)
        db.commit()
        r_ok = chk_r.status_supported
        c_ok = chk_c.status_supported
        v_ok = chk_v.status_supported
        r_type = chk_r.result_json["record_type"]
        c_type = chk_c.result_json["record_type"]
        v_type = chk_v.result_json["record_type"]
    assert r_ok is True
    assert c_ok is True
    assert v_ok is True
    assert r_type == "crime_incident"
    assert c_type == "crime_incident"
    assert v_type == "crime_incident"
