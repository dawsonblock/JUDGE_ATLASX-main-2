"""Confidence scoring engine.

Provides deterministic, rule-based confidence calculations for entity
resolution, edge weighting, and claim reliability.  No ML or LLM calls
are made — all logic is explicit arithmetic.
"""

from __future__ import annotations

import math


def weighted_confidence(
    scores: list[float],
    weights: list[float] | None = None,
) -> float:
    """Compute a weighted average confidence from multiple signals.

    Args:
        scores:  List of confidence values in [0.0, 1.0].
        weights: Optional parallel list of non-negative weights.
                 If omitted every score is weighted equally.

    Returns:
        Float in [0.0, 1.0].

    Raises:
        ValueError: If scores is empty or weights don't match scores length.
    """
    if not scores:
        raise ValueError("scores must not be empty")

    if weights is not None and len(weights) != len(scores):
        raise ValueError("weights must have the same length as scores")

    clamped = [max(0.0, min(1.0, s)) for s in scores]

    if weights is None:
        return sum(clamped) / len(clamped)

    total_weight = sum(weights)
    if total_weight == 0.0:
        return 0.0

    return sum(s * w for s, w in zip(clamped, weights)) / total_weight


def decay_confidence(
    score: float,
    days_old: float,
    half_life_days: float = 365.0,
) -> float:
    """Apply exponential half-life decay to a confidence score.

    A score of 1.0 will decay to 0.5 after ``half_life_days`` days.

    Args:
        score:          Base confidence value in [0.0, 1.0].
        days_old:       Age of the evidence in days.
        half_life_days: Days until confidence halves (default 365).

    Returns:
        Decayed confidence in (0.0, 1.0].  Never reaches zero.
    """
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    if days_old < 0:
        days_old = 0.0

    decay_factor = math.pow(0.5, days_old / half_life_days)
    return max(0.0, min(1.0, score)) * decay_factor


def merge_confidence(scores: list[float]) -> float:
    """Merge multiple independent confidence scores via geometric mean.

    The geometric mean penalises low-confidence outliers more than the
    arithmetic mean, which is appropriate when all signals must agree.

    Args:
        scores: List of confidence values in [0.0, 1.0].

    Returns:
        Geometric mean float in [0.0, 1.0].
    """
    if not scores:
        raise ValueError("scores must not be empty")

    clamped = [max(1e-9, min(1.0, s)) for s in scores]
    log_sum = sum(math.log(s) for s in clamped)
    return math.exp(log_sum / len(clamped))


def propagate_confidence(base: float, edge_weight: float) -> float:
    """Multiply confidence along a graph edge.

    Used when traversing the graph: each hop reduces confidence by the
    edge's own weight.

    Args:
        base:        Confidence at the source node.
        edge_weight: Weight of the edge in [0.0, 1.0].

    Returns:
        Propagated confidence, clamped to [0.0, 1.0].
    """
    return max(0.0, min(1.0, base * edge_weight))
