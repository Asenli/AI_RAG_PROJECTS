"""Sparse embedding service — Qdrant BM25 vectors via FastEmbed."""
import logging
from typing import Iterable

from qdrant_client.models import SparseVector

from app.config import settings

logger = logging.getLogger(__name__)


class SparseEmbeddingService:
    def __init__(self):
        self.model_name = settings.sparse_embedding_model
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from fastembed import SparseTextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "fastembed is required for Qdrant BM25 hybrid search. "
                    "Install backend requirements, then re-run ingestion."
                ) from exc
            logger.info("Loading sparse embedding model: %s", self.model_name)
            self._model = SparseTextEmbedding(model_name=self.model_name)
        return self._model

    def embed_query(self, text: str) -> SparseVector:
        """Embed a query string as a sparse BM25 vector."""
        embedding = next(iter(self.model.query_embed(text)))
        return self._to_qdrant_sparse_vector(embedding)

    def embed_documents(self, texts: Iterable[str]) -> list[SparseVector]:
        """Embed document strings as sparse BM25 vectors."""
        return [
            self._to_qdrant_sparse_vector(embedding)
            for embedding in self.model.embed(list(texts))
        ]

    @staticmethod
    def _to_qdrant_sparse_vector(embedding) -> SparseVector:
        indices = embedding.indices
        values = embedding.values
        if hasattr(indices, "tolist"):
            indices = indices.tolist()
        if hasattr(values, "tolist"):
            values = values.tolist()
        return SparseVector(indices=list(indices), values=list(values))


sparse_embedding_service = SparseEmbeddingService()
