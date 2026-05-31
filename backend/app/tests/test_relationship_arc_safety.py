"""Safety regression tests for the relationship arc publication policy.

Focuses on the causal/blame/guilt predicate blocklist patterns not already
parametrized in test_relationship_arc_policy.py, plus edge-case behaviours
of evaluate_arc_request that are critical for preventing harmful content from
reaching the public API.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.policies.relationship_arc_policy import (
    _has_causal_label,
    evaluate_arc_request,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    enabled: bool = True,
    min_evidence: int = 1,
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
    evidence_count: int = 2,
) -> object:
    return SimpleNamespace(
        predicate=predicate,
        evidence_refs=[{"evidence_id": i} for i in range(evidence_count)],
        status="active",
    )


# ---------------------------------------------------------------------------
# _has_causal_label: untested sub-patterns from the blocklist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "blamed_for",          # blam
        "abused_power",        # abus
        "defamed_victim",      # defam
        "threatened_witness",  # threaten
        "defrauded_clients",   # defraud
        "criminalized_speech", # criminaliz
        "condemned_act",       # condemn
        "perpetrated_fraud",   # perpetrat
        "orchestrated_scheme", # orchestrat
        "killed_in_custody",   # \bkill (word-boundary prefix)
    ],
)
def test_has_causal_label_matches_remaining_blocklist_patterns(predicate: str) -> None:
    assert _has_causal_label(predicate), f"Expected '{predicate}' to be blocked"


# ---------------------------------------------------------------------------
# Word-boundary guard: "skill/skilled" must NOT be blocked by the \bkill rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "skill",
        "skilled_advocate",
        "unskilled",
    ],
)
def test_has_causal_label_word_boundary_allows_skill(predicate: str) -> None:
    assert not _has_causal_label(predicate), (
        f"'{predicate}' must not match \\bkill (word-boundary guard)"
    )


# ---------------------------------------------------------------------------
# _has_causal_label: neutral / procedural terms do not match
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "presided_over",
        "charged_in",
        "appealed_to",
        "located_at",
        "represents",
        "linked_to",
    ],
)
def test_has_causal_label_returns_false_for_neutral_predicates(predicate: str) -> None:
    assert not _has_causal_label(predicate)


# ---------------------------------------------------------------------------
# Empty input → allowed=False (not covered by existing policy tests)
# ---------------------------------------------------------------------------


def test_empty_edge_list_returns_not_allowed() -> None:
    result = evaluate_arc_request([], _settings())
    assert result.allowed is False
    assert result.arcs_enabled is True
    assert result.filtered_edges == []
    assert "no edges passed" in result.reason


# ---------------------------------------------------------------------------
# Mixed batch: causal and neutral edges together
# Only the neutral edges should survive the policy gate
# ---------------------------------------------------------------------------


def test_mixed_batch_only_neutral_edges_pass() -> None:
    edges = [
        _edge(predicate="murdered_by"),   # blocked — causal
        _edge(predicate="presided_over"), # allowed
        _edge(predicate="corrupted_by"),  # blocked — causal
        _edge(predicate="appealed_to"),   # allowed
    ]
    result = evaluate_arc_request(edges, _settings())

    assert result.allowed is True
    passing_predicates = [e.predicate for e in result.filtered_edges]
    assert "presided_over" in passing_predicates
    assert "appealed_to" in passing_predicates
    assert "murdered_by" not in passing_predicates
    assert "corrupted_by" not in passing_predicates
    assert len(result.filtered_edges) == 2


# ---------------------------------------------------------------------------
# Reason string content
# ---------------------------------------------------------------------------


def test_reason_reports_causal_skip_count() -> None:
    edges = [
        _edge(predicate="guilty_verdict"),
        _edge(predicate="conspired_with"),
    ]
    result = evaluate_arc_request(edges, _settings())

    assert result.allowed is False
    assert "2" in result.reason or "causal" in result.reason.lower()


def test_reason_reports_passed_count_on_success() -> None:
    edges = [_edge(predicate="presided_over"), _edge(predicate="located_at")]
    result = evaluate_arc_request(edges, _settings())

    assert result.allowed is True
    assert "2" in result.reason


# ---------------------------------------------------------------------------
# Evidence gate + causal gate interact correctly
# An edge that fails evidence is NOT counted as a causal skip
# ---------------------------------------------------------------------------


def test_evidence_failure_is_separate_from_causal_skip() -> None:
    edges = [
        _edge(predicate="presided_over", evidence_count=0),  # fails evidence gate
        _edge(predicate="guilty_verdict", evidence_count=3), # fails causal gate
    ]
    result = evaluate_arc_request(edges, _settings(min_evidence=1))

    assert result.allowed is False
    # Both must be mentioned in the reason
    assert "below min-evidence" in result.reason
    assert "causal" in result.reason.lower()
