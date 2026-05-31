"""Tests for canonical source key registry (Phase 1)."""

from __future__ import annotations

import pytest

from app.ingestion.source_keys import (
    CANONICAL_SOURCE_KEYS,
    LEGACY_SOURCE_ALIASES,
    SASKATOON_OPEN_DATA_CRIME,
    STATSCAN_CCJS_CRIME_SK,
    WEB_MONITOR_SASKATOON_POLICE_NEWS,
    is_canonical_source_key,
    resolve_source_key,
)

# ---------------------------------------------------------------------------
# Named constants have correct string values
# ---------------------------------------------------------------------------


def test_named_constant_values():
    assert SASKATOON_OPEN_DATA_CRIME == "saskatoon_open_data_crime"
    assert STATSCAN_CCJS_CRIME_SK == "statscan_ccjs_crime_sk"
    assert WEB_MONITOR_SASKATOON_POLICE_NEWS == "web_monitor_saskatoon_police_news"


# ---------------------------------------------------------------------------
# CANONICAL_SOURCE_KEYS membership
# ---------------------------------------------------------------------------


def test_all_named_constants_in_canonical_set():
    from app.ingestion import source_keys as sk

    named = [
        sk.SASKATOON_OPEN_DATA_CRIME,
        sk.SASKATOON_POLICE_OPEN_DATA,
        sk.WEB_MONITOR_SASKATOON_POLICE_NEWS,
        sk.SK_COURTS_QB_DECISIONS,
        sk.SK_COURTS_CA_DECISIONS,
        sk.STATSCAN_CCJS_CRIME_SK,
        sk.STATSCAN_UCR_NATIONAL,
        sk.CANLII_SK,
        sk.FEDERAL_COURT_CANADA,
        sk.SCC_DECISIONS,
        sk.SK_JUSTICE_MINISTRY,
        sk.SK_LEGISLATURE_HANSARD,
        sk.CANADA_OPEN_DATA_CRIME,
        sk.RCMP_SK_NEWS,
        sk.JUSTICE_CANADA_LAWS_XML,
        sk.CANADA_JUSTICE_LAWS,
        sk.SASKATOON_OPEN_DATA_PORTAL,
        sk.COURTLISTENER_BULK,
    ]
    for key in named:
        assert key in CANONICAL_SOURCE_KEYS, f"{key!r} not in CANONICAL_SOURCE_KEYS"


# ---------------------------------------------------------------------------
# is_canonical_source_key
# ---------------------------------------------------------------------------


def test_is_canonical_true_for_canonical():
    assert is_canonical_source_key("saskatoon_open_data_crime") is True


def test_is_canonical_false_for_legacy():
    assert is_canonical_source_key("saskatoon_crime") is False
    assert is_canonical_source_key("statscan") is False
    assert is_canonical_source_key("chicago_crime") is False


# ---------------------------------------------------------------------------
# resolve_source_key — alias resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("saskatoon_crime", SASKATOON_OPEN_DATA_CRIME),
        ("statscan", STATSCAN_CCJS_CRIME_SK),
        ("statscan_crime", STATSCAN_CCJS_CRIME_SK),
        ("statscan_crime_sk", STATSCAN_CCJS_CRIME_SK),
        ("gdelt", WEB_MONITOR_SASKATOON_POLICE_NEWS),
    ],
)
def test_resolve_alias_to_canonical(alias: str, expected: str):
    assert resolve_source_key(alias) == expected


@pytest.mark.parametrize(
    "disabled", ["chicago_crime", "toronto_crime", "la_crime", "fbi_crime"]
)
def test_resolve_disabled_source_returns_none(disabled: str):
    assert resolve_source_key(disabled) is None


def test_resolve_canonical_key_returns_itself():
    for key in CANONICAL_SOURCE_KEYS:
        assert (
            resolve_source_key(key) == key
        ), f"canonical key {key!r} should pass through"


def test_resolve_unknown_key_returns_itself():
    assert (
        resolve_source_key("some_completely_unknown_key")
        == "some_completely_unknown_key"
    )


# ---------------------------------------------------------------------------
# LEGACY_SOURCE_ALIASES — no legacy key is also a canonical key
# ---------------------------------------------------------------------------


def test_legacy_aliases_not_in_canonical_set():
    for legacy_key in LEGACY_SOURCE_ALIASES:
        assert (
            legacy_key not in CANONICAL_SOURCE_KEYS
        ), f"Legacy alias {legacy_key!r} must not appear in CANONICAL_SOURCE_KEYS"
