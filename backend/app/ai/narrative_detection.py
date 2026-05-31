"""Backward-compatibility shim for narrative_detection.

This module is retained for import compatibility. The canonical implementation
has been moved to narrative_pattern_assistance.py to better reflect the
rule-based, pattern-matching nature of the analysis.
"""
# ruff: noqa: F401, F403
from app.ai.narrative_pattern_assistance import *  # noqa: F401, F403
from app.ai.narrative_pattern_assistance import (
    NarrativeMatch,
    detect_narratives,
    detect_from_text,
    NARRATIVE_PATTERNS,
)
