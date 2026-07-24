"""Embedding service — BAAI/bge-large-zh-v1.5 via SiliconFlow API."""
import logging
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.embedding_base_url,
            timeout=120.0,  # 单次请求最长 2 分钟
        )
        self.model = settings.embedding_model

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        logger.info(f"Embedding query, length={len(text)}")
        response = await self.client.embeddings.create(
            model=self.model, input=[text]
        )
        return response.data[0].embedding

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document strings (max 16 per batch)."""
        logger.info(f"Embedding {len(texts)} documents...")
        all_embeddings = []
        # SiliconFlow 单次最多 16 条，分批处理
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.info(f"  Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}, size={len(batch)}")
            response = await self.client.embeddings.create(
                model=self.model, input=batch
            )
            all_embeddings.extend([d.embedding for d in response.data])
        logger.info(f"Embedding complete, got {len(all_embeddings)} vectors")
        return all_embeddings


embedding_service = EmbeddingService()
