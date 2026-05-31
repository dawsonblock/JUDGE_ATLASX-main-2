"""Backward-compatibility shim for trust_propagation.

This module is retained for import compatibility. The canonical implementation
has been moved to evidence_support_weighting.py to better reflect the
deterministic, evidence-based nature of the weighting logic.
"""
# ruff: noqa: F401, F403
from app.ai.evidence_support_weighting import *  # noqa: F401, F403
from app.ai.evidence_support_weighting import (
    TrustScore,
    get_trust_tier,
    compute_trust,
    propagate_trust,
    TRUST_DECAY,
)
