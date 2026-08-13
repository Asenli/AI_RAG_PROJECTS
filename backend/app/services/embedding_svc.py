"""Embedding service — BAAI/bge-large-zh-v1.5 via SiliconFlow API."""
import logging
import os
import time

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


class EmbeddingService:
    def __init__(self):
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None
        if proxy:
            logger.info("EmbeddingService using proxy: %s", proxy)

        self.client = OpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.embedding_base_url,
            timeout=120.0,
        )
        self.model = settings.embedding_model

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Call the embedding API (sync) with retry + exponential backoff."""
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.embeddings.create(
                    model=self.model, input=texts
                )
                return [d.embedding for d in response.data]
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  [重试] embedding 第{attempt+1}次失败: {exc}，{delay:.0f}s 后重试...")
                    time.sleep(delay)
                    self.client = OpenAI(
                        api_key=settings.siliconflow_api_key,
                        base_url=settings.embedding_base_url,
                        timeout=120.0,
                    )
        raise last_error  # type: ignore[misc]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        logger.info("Embedding query, length=%d", len(text))
        embeddings = self._embed_with_retry([text])
        return embeddings[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document strings (max 16 per batch)."""
        logger.info("Embedding %d documents...", len(texts))
        all_embeddings = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.info(
                "  Embedding batch %d/%d, size=%d",
                i // batch_size + 1,
                (len(texts) - 1) // batch_size + 1,
                len(batch),
            )
            embeddings = self._embed_with_retry(batch)
            all_embeddings.extend(embeddings)
        logger.info("Embedding complete, got %d vectors", len(all_embeddings))
        return all_embeddings


embedding_service = EmbeddingService()
