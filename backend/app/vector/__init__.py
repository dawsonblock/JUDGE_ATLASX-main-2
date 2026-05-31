"""Vector module for semantic search and embeddings.

Provides pgvector integration for storing and querying
vector embeddings of claims and evidence.
"""

from app.vector.vector_client import VectorClient, get_vector_client
from app.vector.embedding_service import (
    EmbeddingService,
    get_embedding_service,
)
from app.vector.vector_search import VectorSearch, get_vector_search

__all__ = [
    "VectorClient",
    "get_vector_client",
    "EmbeddingService",
    "get_embedding_service",
    "VectorSearch",
    "get_vector_search",
]
