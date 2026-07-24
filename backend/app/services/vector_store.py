"""Vector Store — Qdrant wrapper for embedding storage and retrieval."""
import hashlib
import logging
import os
import re
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchText,
    MatchValue,
    Modifier,
    Prefetch,
    FilterSelector,
    SparseVector,
    SparseVectorParams,
)
from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = settings.qdrant_collection
DIMENSION = settings.qdrant_dimension
DENSE_VECTOR_NAME = settings.qdrant_dense_vector_name
SPARSE_VECTOR_NAME = settings.qdrant_sparse_vector_name


class VectorStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = None
        self._hybrid_enabled = False

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._init_client()
        return self._client

    def _init_client(self):
        if settings.qdrant_mode == "local":
            db_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "qdrant_data")
            )
            os.makedirs(db_dir, exist_ok=True)
            self._client = QdrantClient(path=db_dir)
        else:
            self._client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
        self._ensure_collection()

    def _ensure_collection(self):
        if self._client.collection_exists(COLLECTION_NAME):
            self._hybrid_enabled = self._collection_supports_hybrid()
            if not self._hybrid_enabled:
                logger.warning(
                    "Qdrant collection %s exists but is not hybrid. "
                    "Run ingestion with --recreate to enable dense + BM25 search.",
                    COLLECTION_NAME,
                )
            return

        self._create_hybrid_collection()

    def _create_hybrid_collection(self):
        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=DIMENSION,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams(
                    modifier=Modifier.IDF,
                ),
            },
        )
        self._hybrid_enabled = True

    def recreate_collection(self):
        """Drop and recreate the collection with hybrid dense + BM25 schema."""
        client = self.client
        if client.collection_exists(COLLECTION_NAME):
            client.delete_collection(COLLECTION_NAME)
            try:
                client.close()
            except Exception:
                pass
            self._client = None

        self.client  # reinitialize after local collection deletion
        if self.count() > 0:
            self.clear_collection()

    def clear_collection(self):
        """Delete all points from the collection without changing its schema."""
        point_ids = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.extend([p.id for p in points])
            if offset is None:
                break

        for i in range(0, len(point_ids), 256):
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=point_ids[i : i + 256],
                wait=True,
            )

    def _collection_supports_hybrid(self) -> bool:
        try:
            info = self._client.get_collection(COLLECTION_NAME)
            params = info.config.params
            vectors = params.vectors
            sparse_vectors = getattr(params, "sparse_vectors", None)

            has_dense = (
                isinstance(vectors, dict) and DENSE_VECTOR_NAME in vectors
            )
            has_sparse = (
                isinstance(sparse_vectors, dict)
                and SPARSE_VECTOR_NAME in sparse_vectors
            )
            return has_dense and has_sparse
        except Exception as exc:
            logger.warning("Failed to inspect Qdrant collection schema: %s", exc)
            return False

    def search(
        self,
        query_vector: list[float],
        sparse_vector: SparseVector | None = None,
        top_k: int = 20,
        filter_expr: str = None,
        company_id: str | None = None,
    ) -> list[dict]:
        """Hybrid search with optional filter expression.

        filter_expr supports a filter expression string format:
          (module == "X" or module == "Y") or (role like "%all%")
        Parsed into Qdrant Filter internally.
        """
        qdrant_filter = self._build_filter(
            filter_expr=filter_expr,
            company_id=company_id or settings.default_company_id,
        )

        if sparse_vector is not None and self._hybrid_enabled:
            return self._hybrid_search(
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
            )

        return self._single_search(
            query=query_vector,
            using=DENSE_VECTOR_NAME if self._hybrid_enabled else None,
            top_k=top_k,
            qdrant_filter=qdrant_filter,
        )

    def debug_search(
        self,
        query_vector: list[float],
        sparse_vector: SparseVector | None = None,
        top_k: int = 20,
        filter_expr: str = None,
        company_id: str | None = None,
    ) -> dict[str, list[dict]]:
        """Return independent dense, BM25 sparse, and RRF hybrid results."""
        qdrant_filter = self._build_filter(
            filter_expr=filter_expr,
            company_id=company_id or settings.default_company_id,
        )
        dense_results = self._single_search(
            query=query_vector,
            using=DENSE_VECTOR_NAME if self._hybrid_enabled else None,
            top_k=top_k,
            qdrant_filter=qdrant_filter,
        )

        bm25_results = []
        hybrid_results = dense_results
        if sparse_vector is not None and self._hybrid_enabled:
            bm25_results = self._single_search(
                query=sparse_vector,
                using=SPARSE_VECTOR_NAME,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
            )
            hybrid_results = self._hybrid_search(
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
            )

        return {
            "dense": dense_results,
            "bm25": bm25_results,
            "hybrid": hybrid_results,
        }

    def _single_search(
        self,
        query,
        using: str | None,
        top_k: int,
        qdrant_filter: Filter | None,
    ) -> list[dict]:
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query,
            using=using,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return self._format_results(response.points)

    def _hybrid_search(
        self,
        query_vector: list[float],
        sparse_vector: SparseVector,
        top_k: int,
        qdrant_filter: Filter | None,
    ) -> list[dict]:
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(
                    query=query_vector,
                    using=DENSE_VECTOR_NAME,
                    filter=qdrant_filter,
                    limit=top_k,
                ),
                Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR_NAME,
                    filter=qdrant_filter,
                    limit=top_k,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return self._format_results(response.points)

    @staticmethod
    def _format_results(results) -> list[dict]:
        return [
            {
                "id": r.id,
                "distance": r.score,
                "entity": r.payload or {},
            }
            for r in results
        ]

    def _build_filter(
        self,
        filter_expr: str = None,
        company_id: str | None = None,
    ) -> Filter | None:
        """Parse filter expression string into Qdrant Filter.

        Supported patterns:
        - (module == "X") or (role like "%all%")
        - (module == "X" or module == "Y") or (role like "%all%")
        """
        must_conditions = []
        should_conditions = []

        if company_id:
            must_conditions.append(
                FieldCondition(
                    key="company_id",
                    match=MatchValue(value=str(company_id)),
                )
            )

        if not filter_expr:
            return Filter(must=must_conditions) if must_conditions else None

        # Extract module == "X" patterns
        module_matches = re.findall(r'module\s*==\s*"([^"]+)"', filter_expr)
        if len(module_matches) == 1:
            should_conditions.append(
                FieldCondition(key="module", match=MatchAny(any=[module_matches[0]]))
            )
        elif len(module_matches) > 1:
            should_conditions.append(
                FieldCondition(key="module", match=MatchAny(any=module_matches))
            )

        # Extract role like "%all%" → match role == "all" or role contains "all"
        if 'role like "%all%"' in filter_expr or "role like '%all%'" in filter_expr:
            should_conditions.append(
                FieldCondition(key="role", match=MatchText(text="all"))
            )

        if not should_conditions:
            return Filter(must=must_conditions) if must_conditions else None
        return Filter(must=must_conditions, should=should_conditions)

    def insert(
        self,
        vectors: list[list[float]],
        sparse_vectors: list[SparseVector] | None,
        metadata_list: list[dict],
    ) -> dict:
        if sparse_vectors is not None and not self._hybrid_enabled:
            raise RuntimeError(
                f"Qdrant collection '{COLLECTION_NAME}' is dense-only. "
                "Run `python -m scripts.ingest --recreate` to rebuild it "
                "with dense + BM25 vectors."
            )

        points = []
        if sparse_vectors is not None and len(vectors) != len(sparse_vectors):
            raise ValueError("dense and sparse vector counts do not match")

        sparse_iter = sparse_vectors or [None] * len(vectors)
        for vec, sparse_vec, meta in zip(vectors, sparse_iter, metadata_list):
            payload = {}
            for k, v in meta.items():
                if k != "vector":
                    payload[k] = v
            payload["company_id"] = str(
                payload.get("company_id") or settings.default_company_id
            )
            point_id = self._point_id(payload)

            point_vector = (
                {
                    DENSE_VECTOR_NAME: vec,
                    SPARSE_VECTOR_NAME: sparse_vec,
                }
                if sparse_vec is not None
                else vec
            )
            points.append(PointStruct(id=point_id, vector=point_vector, payload=payload))

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )
        return {"insert_count": len(points)}

    @staticmethod
    def _point_id(payload: dict) -> int:
        key = "|".join([
            str(payload.get("company_id", settings.default_company_id)),
            str(payload.get("source", "")),
            str(payload.get("chunk_index", "")),
            str(payload.get("header_path", "")),
        ])
        digest = hashlib.sha1(key.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF

    def delete_by_source(
        self,
        source: str,
        company_id: str | None = None,
    ) -> dict:
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="company_id",
                            match=MatchValue(
                                value=str(company_id or settings.default_company_id)
                            ),
                        ),
                        FieldCondition(key="source", match=MatchValue(value=source)),
                    ]
                )
            ),
            wait=True,
        )
        return {
            "status": "deleted",
            "company_id": str(company_id or settings.default_company_id),
            "source": source,
        }

    def count(self, company_id: str | None = None) -> int:
        try:
            count_filter = None
            if company_id is not None:
                count_filter = Filter(
                    must=[
                        FieldCondition(
                            key="company_id",
                            match=MatchValue(value=str(company_id)),
                        )
                    ]
                )
            result = self.client.count(
                collection_name=COLLECTION_NAME,
                count_filter=count_filter,
                exact=True,
            )
            return result.count
        except Exception:
            return 0

    def list_sources(self, company_id: str | None = None) -> list[str]:
        try:
            points, _ = self.client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="company_id",
                            match=MatchValue(
                                value=str(company_id or settings.default_company_id)
                            ),
                        )
                    ]
                ),
                with_payload=["source"],
                limit=10000,
            )
            seen = set()
            for p in points:
                if p.payload and "source" in p.payload:
                    seen.add(p.payload["source"])
            return sorted(list(seen))
        except Exception:
            return []

    def list_source_stats(self, company_id: str | None = None) -> list[dict]:
        """Return one summary record per source in the collection."""
        try:
            stats = {}
            offset = None
            cid = str(company_id or settings.default_company_id)
            while True:
                points, offset = self.client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="company_id",
                                match=MatchValue(value=cid),
                            )
                        ]
                    ),
                    with_payload=[
                        "company_id",
                        "source",
                        "module",
                        "sub_module",
                        "knowledge_type",
                        "role",
                        "version",
                        "upload_channel",
                    ],
                    limit=1000,
                    offset=offset,
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    source = payload.get("source")
                    if not source:
                        continue
                    if source not in stats:
                        stats[source] = {
                            "company_id": payload.get("company_id", cid),
                            "source": source,
                            "chunks": 0,
                            "module": payload.get("module", ""),
                            "sub_module": payload.get("sub_module", ""),
                            "knowledge_type": payload.get("knowledge_type", ""),
                            "role": payload.get("role", "all"),
                            "version": payload.get("version", ""),
                            "upload_channel": payload.get("upload_channel", ""),
                        }
                    stats[source]["chunks"] += 1
                if offset is None:
                    break
            return sorted(stats.values(), key=lambda item: item["source"])
        except Exception:
            return []

    def get_by_source(
        self,
        source: str,
        company_id: str | None = None,
    ) -> list[dict]:
        """Return all chunks for a source, sorted by chunk index."""
        try:
            cid = str(company_id or settings.default_company_id)
            points, _ = self.client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="company_id",
                            match=MatchValue(value=cid),
                        ),
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=source),
                        )
                    ]
                ),
                with_payload=True,
                with_vectors=False,
                limit=10000,
            )
            chunks = []
            for point in points:
                payload = point.payload or {}
                chunks.append({
                    "id": point.id,
                    "company_id": payload.get("company_id", cid),
                    "text": payload.get("text", ""),
                    "module": payload.get("module", ""),
                    "sub_module": payload.get("sub_module", ""),
                    "knowledge_type": payload.get("knowledge_type", ""),
                    "role": payload.get("role", "all"),
                    "header_path": payload.get("header_path", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "chunk_part": payload.get("chunk_part"),
                    "chunk_parts": payload.get("chunk_parts"),
                    "version": payload.get("version", ""),
                    "priority": payload.get("priority", 1.0),
                    "upload_channel": payload.get("upload_channel", ""),
                })
            return sorted(chunks, key=lambda item: item.get("chunk_index", 0))
        except Exception:
            return []

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None


vector_store = VectorStore()
