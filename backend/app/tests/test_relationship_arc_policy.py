"""Unit tests for app.policies.relationship_arc_policy.

These tests are pure unit tests — no database or network required.
Eight cases cover the full policy decision surface.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.policies.relationship_arc_policy import (
    evaluate_arc_request,
    _has_causal_label,
)


_UNSET = object()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    enabled: bool = True,
    min_evidence: int = 2,
    max_results: int = 250,
) -> object:
    return SimpleNamespace(
        enable_public_relationship_arcs=enabled,
        public_relationship_arc_min_evidence=min_evidence,
        public_relationship_arc_max_results=max_results,
    )


def _edge(
    *,
    predicate: str = "presided_over",
    evidence_refs: list | None | object = _UNSET,
    status: str = "active",
) -> object:
    refs = [{"evidence_id": 1}, {"evidence_id": 2}] if evidence_refs is _UNSET else evidence_refs
    return SimpleNamespace(predicate=predicate, evidence_refs=refs, status=status)


# ---------------------------------------------------------------------------
# Test 1 — feature flag disabled → empty list, arcs_enabled=False
# ---------------------------------------------------------------------------


def test_disabled_config_returns_empty() -> None:
    settings = _settings(enabled=False)
    result = evaluate_arc_request([_edge()], settings)

    assert result.allowed is False
    assert result.arcs_enabled is False
    assert result.filtered_edges == []


# ---------------------------------------------------------------------------
# Test 2 — zero evidence refs → excluded
# ---------------------------------------------------------------------------


def test_no_evidence_excluded() -> None:
    settings = _settings(enabled=True, min_evidence=1)
    result = evaluate_arc_request([_edge(evidence_refs=[])], settings)

    assert result.allowed is False
    assert result.filtered_edges == []


# ---------------------------------------------------------------------------
# Test 3 — below minimum evidence count → excluded
# ---------------------------------------------------------------------------


def test_below_min_evidence_excluded() -> None:
    settings = _settings(enabled=True, min_evidence=3)
    result = evaluate_arc_request(
        [_edge(evidence_refs=[{"evidence_id": 1}, {"evidence_id": 2}])],
        settings,
    )

    assert result.allowed is False
    assert result.filtered_edges == []


# ---------------------------------------------------------------------------
# Test 4 — causal / blame / guilt labels rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "caused",
        "bribed",
        "guilty_verdict",
        "corruption_link",
        "conspired_with",
        "murdered_by",
        "harassed",
        "misconduct",
        "convicted_of",
        "assaulted_officer",
    ],
)
def test_causal_labels_rejected(predicate: str) -> None:
    settings = _settings(enabled=True, min_evidence=1)
    edges = [_edge(predicate=predicate, evidence_refs=[{"evidence_id": 1}, {"evidence_id": 2}, {"evidence_id": 3}])]
    result = evaluate_arc_request(edges, settings)

    assert result.allowed is False
    assert result.filtered_edges == []


# ---------------------------------------------------------------------------
# Test 5 — neutral procedural predicates pass when enabled + evidence met
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "presided_over",
        "charged_in",
        "located_at",
        "appealed_to",
        "represents",
        "linked_to",
        "merged_into",
        "transferred_to",
    ],
)
def test_neutral_predicates_pass_when_enabled(predicate: str) -> None:
    settings = _settings(enabled=True, min_evidence=2)
    edges = [_edge(predicate=predicate, evidence_refs=[{"evidence_id": 1}, {"evidence_id": 2}])]
    result = evaluate_arc_request(edges, settings)

    assert result.allowed is True
    assert len(result.filtered_edges) == 1


# ---------------------------------------------------------------------------
# Test 6 — max_results cap enforced
# ---------------------------------------------------------------------------


def test_max_results_cap_enforced() -> None:
    settings = _settings(enabled=True, min_evidence=1, max_results=3)
    edges = [_edge(evidence_refs=[{"evidence_id": i}]) for i in range(10)]
    result = evaluate_arc_request(edges, settings)

    assert len(result.filtered_edges) == 3


# ---------------------------------------------------------------------------
# Test 7 — disabled flag overrides otherwise-passing edges
# ---------------------------------------------------------------------------


def test_disabled_overrides_passing_edges() -> None:
    settings = _settings(enabled=False, min_evidence=1, max_results=250)
    edges = [
        _edge(predicate="presided_over", evidence_refs=[{"evidence_id": 1}, {"evidence_id": 2}])
    ]
    result = evaluate_arc_request(edges, settings)

    assert result.arcs_enabled is False
    assert result.filtered_edges == []


# ---------------------------------------------------------------------------
# Test 8 — None evidence_refs treated as zero evidence
# ---------------------------------------------------------------------------


def test_none_evidence_refs_treated_as_zero() -> None:
    settings = _settings(enabled=True, min_evidence=1)
    result = evaluate_arc_request([_edge(evidence_refs=None)], settings)

    # evidence_refs=None → _evidence_count returns 0 < min_evidence=1 → excluded
    assert result.allowed is False
    assert result.filtered_edges == []
