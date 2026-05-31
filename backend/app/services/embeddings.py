"""Semantic embeddings service backed by sentence-transformers.

The heavy ``sentence-transformers`` / torch dependency is only imported when
``JTA_EMBEDDINGS_ENABLED=true``.  When disabled every public function behaves
as a no-op so callers never need to branch on the feature flag themselves.

Usage::

    from app.services.embeddings import encode, find_similar_claims

    vec = encode("John Smith convicted of fraud")  # list[float] | None
    similar = find_similar_claims("John Smith fraud", db)   # list[MemoryClaim]
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.entities import MemoryClaim

logger = logging.getLogger(__name__)

# Module-level lazy singleton for the sentence-transformers model.
_model: object | None = None
_model_name: str | None = None


def _get_model() -> object | None:
    """Return a loaded SentenceTransformer model or None if disabled/unavailable."""
    global _model, _model_name  # noqa: PLW0603

    settings = get_settings()
    if not settings.embeddings_enabled:
        return None

    desired = settings.embeddings_model
    if _model is not None and _model_name == desired:
        return _model

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        logger.info("Loading sentence-transformers model: %s", desired)
        _model = SentenceTransformer(desired)
        _model_name = desired
        return _model
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; set JTA_EMBEDDINGS_ENABLED=false "
            "or install the package."
        )
        return None
    except Exception:
        logger.exception("Failed to load embeddings model '%s'", desired)
        return None


def encode(text: str) -> list[float] | None:
    """Encode *text* into a dense vector.

    Returns ``None`` when embeddings are disabled or the model is unavailable.
    The returned list is always plain Python floats (JSON-serialisable).
    """
    model = _get_model()
    if model is None:
        return None
    if not text or not text.strip():
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [float(v) for v in vec]
    except Exception:
        logger.exception("encode() failed for text of length %d", len(text))
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Both vectors are assumed already L2-normalised (as returned by
    ``encode()`` with ``normalize_embeddings=True``), so the dot product
    is equivalent to cosine similarity and is fast to compute without
    introducing a heavy dependency.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    # Clamp to [-1, 1] to guard against floating-point drift
    return max(-1.0, min(1.0, dot))


def _euclidean_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity_unnormed(a: list[float], b: list[float]) -> float:
    """Cosine similarity for vectors that may *not* be L2-normalised."""
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = _euclidean_norm(a)
    norm_b = _euclidean_norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def find_similar_claims(
    text: str,
    db: "Session",
    k: int | None = None,
    threshold: float | None = None,
) -> "list[MemoryClaim]":
    """Return MemoryClaims whose ``claim_embedding`` is similar to *text*.

    When embeddings are disabled or no claims carry embeddings, returns an
    empty list rather than raising.

    Args:
        text: Query text to compare against stored claim embeddings.
        db: SQLAlchemy session (read-only usage).
        k: Maximum results to return.  Defaults to ``settings.embeddings_top_k``.
        threshold: Minimum cosine similarity.  Defaults to
            ``settings.embeddings_similarity_threshold``.

    Returns:
        List of :class:`~app.models.entities.MemoryClaim` objects ordered by
        descending similarity, capped at *k*.
    """
    query_vec = encode(text)
    if query_vec is None:
        return []

    settings = get_settings()
    k = k if k is not None else settings.embeddings_top_k
    threshold = (
        threshold if threshold is not None else settings.embeddings_similarity_threshold
    )

    # Lazy import to avoid circular deps at module load time.
    from app.models.entities import MemoryClaim  # noqa: PLC0415

    try:
        candidates: list[MemoryClaim] = (
            db.query(MemoryClaim)
            .filter(MemoryClaim.claim_embedding.isnot(None))  # type: ignore[attr-defined]
            .all()
        )
    except Exception:
        logger.exception("find_similar_claims: DB query failed")
        return []

    scored: list[tuple[float, MemoryClaim]] = []
    for claim in candidates:
        stored = claim.claim_embedding  # type: ignore[attr-defined]
        if not isinstance(stored, list) or len(stored) != len(query_vec):
            continue
        try:
            sim = cosine_similarity(query_vec, stored)
        except ValueError:
            continue
        if sim >= threshold:
            scored.append((sim, claim))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [claim for _, claim in scored[:k]]
