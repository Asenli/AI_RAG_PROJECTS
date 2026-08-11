"""Configuration loader — environment variables + config.yaml"""
import os
import sys
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

# ===== 显式加载 .env (早于 pydantic-settings) =====
_ENV_LOADED = False


def _find_and_load_dotenv():
    """在模块导入时查找并加载 .env 文件."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    # 查找顺序: 当前工作目录 → backend/ → 项目根目录
    candidates = [
        os.path.join(os.getcwd(), ".env"),           # cwd/.env
        os.path.join(os.path.dirname(__file__), ".env"),  # backend/app/.env
        os.path.join(os.path.dirname(__file__), "..", ".env"),  # backend/.env
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),  # 项目根/.env
    ]
    for candidate in candidates:
        abs_path = os.path.abspath(candidate)
        if os.path.exists(abs_path):
            try:
                # 优先使用 python-dotenv
                from dotenv import load_dotenv
                load_dotenv(abs_path, override=False)
            except ImportError:
                # 兜底：手动解析 .env
                with open(abs_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip("\"'")
                        if key and key not in os.environ:
                            os.environ[key] = val
            _ENV_LOADED = True
            return abs_path
    return None


_ENV_PATH = _find_and_load_dotenv()


class Settings(BaseSettings):
    # === Multi-tenant ===
    default_company_id: str = "1"

    # === LLM (DeepSeek official) ===
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str = "https://api.deepseek.com"

    # === Legacy DeepSeek config (kept for backward-compatible env parsing) ===
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    # === Embedding (SiliconFlow) ===
    siliconflow_api_key: str = ""
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"

    # === Rerank (SiliconFlow) ===
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # === PostgreSQL ===
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_db: str = "food_safety"

    # === Redis ===
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # === MinIO ===
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "knowledge-base"

    # === Qdrant ===
    qdrant_mode: str = "local"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "food_safety_kb"
    qdrant_dimension: int = 1024
    qdrant_dense_vector_name: str = "dense"
    qdrant_sparse_vector_name: str = "bm25"
    sparse_embedding_model: str = "Qdrant/bm25"

    # === JWT ===
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    token_expire_minutes: int = 1440

    # === Retrieval ===
    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    score_threshold: float = 0.65
    fallback_threshold: int = 3

    # === Memory ===
    short_term_max_rounds: int = 5
    session_ttl: int = 1209600  # 14 days
    summary_max_length: int = 500

    # === Prompt Management ===
    prompt_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent / "prompts",
    )
    default_prompt_version: str = "v1.0.0"
    prompt_hot_reload: bool = False
    ab_test_enabled: bool = False
    ab_test_new_version: str = "v1.1.0"
    ab_test_traffic_percent: int = 30
    context_build_mode: str = "standard"
    safety_filter_enabled: bool = True

    class Config:
        env_file = _ENV_PATH or ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def load_yaml_config(path: str = "config.yaml") -> dict:
    """Load non-sensitive config from YAML."""
    for base in [".", "..", os.path.join(os.path.dirname(__file__), "..", "..")]:
        full = os.path.join(base, path)
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    return {}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
yaml_config = load_yaml_config()
