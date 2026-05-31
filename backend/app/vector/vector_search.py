"""Vector search service for semantic search operations.

Provides hybrid search combining keyword search
with vector similarity search for better results.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.vector.embedding_service import get_embedding_service
from app.vector.vector_client import get_vector_client


class VectorSearch:
    """Service for vector-based semantic search.

    Combines keyword search with vector similarity
    for improved search results.
    """

    def __init__(self):
        """Initialize vector search service."""
        self._enabled = get_settings().embeddings_enabled
        self._vector_client = get_vector_client()
        self._embedding_service = get_embedding_service()

    def is_enabled(self) -> bool:
        """Check if vector search is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return (
            self._enabled
            and self._vector_client.is_enabled()
            and self._embedding_service.is_enabled()
        )

    def semantic_search(
        self,
        query: str,
        table_name: str,
        column_name: str,
        limit: int = 10,
        where_clause: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform semantic search using vector similarity.

        Args:
            query: Search query text
            table_name: Table name to search
            column_name: Column name with vector data
            limit: Maximum number of results
            where_clause: Optional WHERE clause for filtering

        Returns:
            List of matching records with similarity scores
        """
        if not self.is_enabled():
            return []

        # Generate embedding for query
        query_embedding = self._embedding_service.embed_text(query)
        if query_embedding is None:
            return []

        # Perform vector similarity search
        return self._vector_client.vector_similarity_search(
            table_name=table_name,
            column_name=column_name,
            query_vector=query_embedding,
            limit=limit,
            where_clause=where_clause,
        )

    def hybrid_search(
        self,
        query: str,
        keyword_results: list[dict[str, Any]],
        table_name: str,
        column_name: str,
        semantic_limit: int = 5,
        where_clause: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform hybrid search combining keyword and semantic.

        Args:
            query: Search query text
            keyword_results: Results from keyword search
            table_name: Table name for semantic search
            column_name: Column name with vector data
            semantic_limit: Number of semantic results to fetch
            where_clause: Optional WHERE clause for filtering

        Returns:
            Combined and ranked results
        """
        if not self.is_enabled():
            return keyword_results

        # Get semantic search results
        semantic_results = self.semantic_search(
            query=query,
            table_name=table_name,
            column_name=column_name,
            limit=semantic_limit,
            where_clause=where_clause,
        )

        # Combine results with ranking
        combined = self._rank_results(
            keyword_results=keyword_results,
            semantic_results=semantic_results,
        )

        return combined

    def _rank_results(
        self,
        keyword_results: list[dict[str, Any]],
        semantic_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank and combine keyword and semantic results.

        Args:
            keyword_results: Results from keyword search
            semantic_results: Results from semantic search

        Returns:
            Combined ranked results
        """
        # Create a map of results by ID
        result_map: dict[int, dict[str, Any]] = {}

        # Add keyword results with keyword score
        for idx, result in enumerate(keyword_results):
            result_id = result.get("id")
            if result_id is not None:
                if result_id not in result_map:
                    result_map[result_id] = result.copy()
                    result_map[result_id]["keyword_score"] = 1.0 - (
                        idx / len(keyword_results)
                    )
                    result_map[result_id]["semantic_score"] = 0.0
                    result_map[result_id]["combined_score"] = (
                        result_map[result_id]["keyword_score"]
                    )

        # Add semantic results with semantic score
        for result in semantic_results:
            result_id = result.get("id")
            similarity = result.get("similarity", 0.0)
            if result_id is not None:
                if result_id not in result_map:
                    result_map[result_id] = result.copy()
                    result_map[result_id]["keyword_score"] = 0.0
                    result_map[result_id]["semantic_score"] = similarity
                    result_map[result_id]["combined_score"] = similarity
                else:
                    # Update existing result
                    result_map[result_id]["semantic_score"] = similarity
                    # Combined score: weighted average
                    result_map[result_id]["combined_score"] = (
                        0.6 * result_map[result_id]["keyword_score"]
                        + 0.4 * similarity
                    )

        # Sort by combined score
        ranked = sorted(
            result_map.values(),
            key=lambda x: x.get("combined_score", 0.0),
            reverse=True,
        )

        return ranked


# Shared vector search instance
_vector_search: VectorSearch | None = None


def get_vector_search() -> VectorSearch:
    """Get or create the shared vector search instance.

    Returns:
        Vector search instance
    """
    global _vector_search
    if _vector_search is None:
        _vector_search = VectorSearch()
    return _vector_search
