"""pgvector client for vector database operations.

Provides PostgreSQL pgvector extension integration
for storing and querying vector embeddings.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.db.session import SessionLocal


class VectorClient:
    """pgvector client for vector database operations.

    Provides methods for storing, indexing, and querying
    vector embeddings using PostgreSQL pgvector extension.
    """

    def __init__(self):
        """Initialize pgvector client."""
        self._enabled = get_settings().embeddings_enabled

    def is_enabled(self) -> bool:
        """Check if pgvector is enabled and available.

        Returns:
            True if enabled, False otherwise
        """
        if not self._enabled:
            return False

        try:
            with SessionLocal() as db:
                # Check if pgvector extension is installed
                result = db.execute(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                return result.scalar() is not None
        except Exception:
            return False

    def ensure_extension(self) -> bool:
        """Ensure pgvector extension is installed.

        Returns:
            True if successful, False otherwise
        """
        if not self._enabled:
            return False

        try:
            with SessionLocal() as db:
                # Install pgvector extension if not present
                db.execute("CREATE EXTENSION IF NOT EXISTS vector")
                db.commit()
                return True
        except Exception:
            return False

    def create_index(
        self,
        table_name: str,
        column_name: str,
        index_type: str = "ivfflat",
        index_params: dict[str, Any] | None = None,
    ) -> bool:
        """Create vector index on a column.

        Args:
            table_name: Table name
            column_name: Column name with vector data
            index_type: Index type (ivfflat, hnsw)
            index_params: Additional index parameters

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            return False

        try:
            with SessionLocal() as db:
                if index_type == "ivfflat":
                    # IVFFlat index for approximate nearest neighbor
                    lists = (
                        index_params.get("lists", 100) if index_params else 100
                    )
                    sql = f"""
                        CREATE INDEX IF NOT EXISTS idx_{table_name}_{column_name}
                        ON {table_name} USING ivfflat ({column_name} vector_cosine_ops)
                        WITH (lists = {lists})
                    """
                elif index_type == "hnsw":
                    # HNSW index for approximate nearest neighbor
                    m = index_params.get("m", 16) if index_params else 16
                    ef_construction = (
                        index_params.get("ef_construction", 64)
                        if index_params
                        else 64
                    )
                    sql = (
                        f"CREATE INDEX IF NOT EXISTS "
                        f"idx_{table_name}_{column_name} "
                        f"ON {table_name} USING hnsw "
                        f"({column_name} vector_cosine_ops) "
                        f"WITH (m = {m}, ef_construction = {ef_construction})"
                    )
                else:
                    return False

                db.execute(sql)
                db.commit()
                return True
        except Exception:
            return False

    def vector_similarity_search(
        self,
        table_name: str,
        column_name: str,
        query_vector: list[float],
        limit: int = 10,
        where_clause: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search.

        Args:
            table_name: Table name
            column_name: Column name with vector data
            query_vector: Query vector
            limit: Maximum number of results
            where_clause: Optional WHERE clause for filtering

        Returns:
            List of matching records with similarity scores
        """
        if not self.is_enabled():
            return []

        try:
            with SessionLocal() as db:
                vector_str = f"[{','.join(map(str, query_vector))}]"
                where_sql = f"WHERE {where_clause}" if where_clause else ""

                sql = f"""
                    SELECT *, 1 - ({column_name} <=> %s::vector) as similarity
                    FROM {table_name}
                    {where_sql}
                    ORDER BY {column_name} <=> %s::vector
                    LIMIT %s
                """

                result = db.execute(sql, (vector_str, vector_str, limit))
                return [dict(row._mapping) for row in result]
        except Exception:
            return []


# Shared vector client instance
_vector_client: VectorClient | None = None


def get_vector_client() -> VectorClient:
    """Get or create the shared vector client instance.

    Returns:
        Vector client instance
    """
    global _vector_client
    if _vector_client is None:
        _vector_client = VectorClient()
    return _vector_client
