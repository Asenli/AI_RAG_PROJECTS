"""Rerank service — BAAI/bge-reranker-v2-m3 via SiliconFlow API."""
import httpx
from app.config import settings


class RerankService:
    def __init__(self):
        self.base_url = settings.embedding_base_url
        self.model = settings.rerank_model
        self.api_key = settings.siliconflow_api_key

    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[dict]:
        """Rerank documents by relevance to query. Returns list of {index, relevance_score}."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/rerank",
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            data = response.json()
            if response.status_code != 200:
                # Fallback: return original order with dummy scores
                return [
                    {"index": i, "relevance_score": 0.5}
                    for i in range(min(top_n, len(documents)))
                ]
            return data.get("results", [])


rerank_service = RerankService()
