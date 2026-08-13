#!/bin/bash
# ============================================================
# 售后智能助手 — 后端启动入口
# 等待所有依赖服务就绪后启动 FastAPI
# ============================================================
set -e

echo "============================================"
echo "  售后智能助手 — 后端启动中..."
echo "============================================"

# ── Helper: wait for TCP port ──
wait_for_port() {
    local host="$1"
    local port="$2"
    local name="$3"
    local max_wait="${4:-60}"

    echo "  ⏳ 等待 ${name} (${host}:${port})..."
    local waited=0
    until curl -s --max-time 2 "http://${host}:${port}" >/dev/null 2>&1 || \
          timeout 2 bash -c "echo >/dev/tcp/${host}/${port}" 2>/dev/null; do
        sleep 2
        waited=$((waited + 2))
        if [ "$waited" -ge "$max_wait" ]; then
            echo "  ⚠️  ${name} 在 ${max_wait}s 内未就绪，继续启动..."
            break
        fi
    done
    echo "  ✅ ${name} 已就绪"
}

wait_for_http() {
    local url="$1"
    local name="$2"
    local max_wait="${3:-60}"

    echo "  ⏳ 等待 ${name} (${url})..."
    local waited=0
    until curl -sf --max-time 3 "${url}" >/dev/null 2>&1; do
        sleep 3
        waited=$((waited + 3))
        if [ "$waited" -ge "$max_wait" ]; then
            echo "  ❌ ${name} 在 ${max_wait}s 内未就绪"
            return 1
        fi
    done
    echo "  ✅ ${name} 已就绪"
}

http_base_url() {
    case "$1" in
        http://*|https://*) echo "$1" ;;
        *) echo "http://$1" ;;
    esac
}

# ── 1. Wait for PostgreSQL ──
echo "[1/5] 检查数据库连接..."
wait_for_port "${PG_HOST:-postgres}" "${PG_PORT:-5432}" "PostgreSQL" 60

# ── 2. Wait for Redis ──
echo "[2/5] 检查 Redis 连接..."
wait_for_port "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "Redis" 30

# ── 3. Wait for Qdrant ──
echo "[3/5] 检查 Qdrant 连接..."
wait_for_http "http://${QDRANT_HOST:-qdrant}:${QDRANT_PORT:-6333}/healthz" "Qdrant" 90

# ── 4. Wait for MinIO ──
echo "[4/5] 检查 MinIO 连接..."
MINIO_BASE="$(http_base_url "${MINIO_ENDPOINT:-minio:9000}")"
wait_for_http "${MINIO_BASE}/minio/health/live" "MinIO" 60

# ── 5. Initialize database tables ──
echo "[5/5] 初始化数据库表..."

python -c "
import asyncio
from app.models.base import engine, Base
import app.models.memory
import app.models.ticket
import app.models.feedback
import app.models.trace
import app.models.user
from app.main import ensure_company_columns

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_company_columns(conn)
    print('  ✅ 数据库表已就绪')

asyncio.run(init_db())
"

echo ""
echo "============================================"
echo "  启动 FastAPI 服务..."
echo "============================================"

# Execute the CMD
exec "$@"
