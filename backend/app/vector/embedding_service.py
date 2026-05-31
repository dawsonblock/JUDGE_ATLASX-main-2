"""Embedding service for generating text embeddings.

Provides text-to-vector embedding generation using
configured embedding models (OpenAI, SentenceTransformers, etc.).
"""

from __future__ import annotations

from app.core.config import get_settings


class EmbeddingService:
    """Service for generating text embeddings.

    Supports multiple embedding backends including
    OpenAI, SentenceTransformers, and custom models.
    """

    def __init__(self):
        """Initialize embedding service."""
        self._enabled = get_settings().embeddings_enabled
        self._model = None
        self._backend = getattr(get_settings(), "embeddings_backend", "openai")

    def is_enabled(self) -> bool:
        """Check if embedding service is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return self._enabled

    def _load_model(self) -> bool:
        """Load the embedding model.

        Returns:
            True if successful, False otherwise
        """
        if self._model is not None:
            return True

        try:
            if self._backend == "openai":
                # OpenAI embeddings
                import openai

                openai.api_key = getattr(
                    get_settings(), "openai_api_key", None
                )
                self._model = openai
                return True
            elif self._backend == "sentence_transformers":
                # SentenceTransformers
                from sentence_transformers import SentenceTransformer

                model_name = getattr(
                    get_settings(),
                    "embeddings_model",
                    "all-MiniLM-L6-v2",
                )
                self._model = SentenceTransformer(model_name)
                return True
            else:
                return False
        except Exception:
            return False

    def embed_text(self, text: str) -> list[float] | None:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if failed
        """
        if not self.is_enabled():
            return None

        if not self._load_model():
            return None

        try:
            if self._backend == "openai":
                response = self._model.Embedding.create(
                    input=text,
                    model="text-embedding-ada-002",
                )
                return response["data"][0]["embedding"]
            elif self._backend == "sentence_transformers":
                embedding = self._model.encode(text)
                return embedding.tolist()
            else:
                return None
        except Exception:
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (None for failed embeddings)
        """
        if not self.is_enabled():
            return [None] * len(texts)

        if not self._load_model():
            return [None] * len(texts)

        try:
            if self._backend == "openai":
                # OpenAI batch embedding
                response = self._model.Embedding.create(
                    input=texts,
                    model="text-embedding-ada-002",
                )
                return [item["embedding"] for item in response["data"]]
            elif self._backend == "sentence_transformers":
                embeddings = self._model.encode(texts)
                return embeddings.tolist()
            else:
                return [None] * len(texts)
        except Exception:
            return [None] * len(texts)

    def get_embedding_dimension(self) -> int | None:
        """Get the dimension of the embedding vectors.

        Returns:
            Embedding dimension or None if unknown
        """
        if self._backend == "openai":
            return 1536  # text-embedding-ada-002 dimension
        elif self._backend == "sentence_transformers":
            model_name = getattr(
                get_settings(),
                "embeddings_model",
                "all-MiniLM-L6-v2",
            )
            # Common dimensions for popular models
            if "MiniLM-L6-v2" in model_name:
                return 384
            elif "all-mpnet-base-v2" in model_name:
                return 768
            else:
                return None
        else:
            return None


# Shared embedding service instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the shared embedding service instance.

    Returns:
        Embedding service instance
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
