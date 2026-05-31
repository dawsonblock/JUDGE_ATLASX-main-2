"""Backward-compatibility shim for source_bias_analysis.

This module is retained for import compatibility. The canonical implementation
has been moved to source_perspective_assistance.py to better reflect the
rule-based, non-opinionated nature of the analysis.
"""
# ruff: noqa: F401, F403
from app.ai.source_perspective_assistance import *  # noqa: F401, F403
from app.ai.source_perspective_assistance import (
    BiasReport,
    analyze_source_text,
    BIAS_INDICATORS,
)
