# 食安团餐售后智能助手部署说明

当前项目不需要本地 GPU。LLM 使用 DeepSeek 官方 API，Embedding 和 Rerank 使用 SiliconFlow，向量库使用 Qdrant dense + BM25 hybrid schema。

## 端口

- 本地开发前端：`http://localhost:5173`
- 本地开发后端：`http://localhost:5002`
- Docker 前端：`http://服务器IP:5001`
- Docker 后端：`http://服务器IP:5002`
- Docker 后端容器内端口：`8000`

## 必填环境变量

复制环境变量模板：

```bash
cp .env.example .env
```

至少填写：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek 官方 API Key
SILICONFLOW_API_KEY=你的 SiliconFlow API Key
PG_PASSWORD=强密码
REDIS_PASSWORD=强密码
MINIO_SECRET_KEY=强密码
JWT_SECRET=强随机字符串
```

默认模型配置：

```bash
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
RERANK_MODEL=BAAI/bge-reranker-v2-m3
DEFAULT_COMPANY_ID=1
COMPANY_ID=1
```

## 本地开发启动

Windows：

```powershell
cd D:\AI_Projects\food-safety-assistant
.\start.ps1
```

Linux：

```bash
cd /path/to/food-safety-assistant
bash start.sh
```

手动启动后端：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 5002 --reload
```

手动启动前端：

```bash
cd frontend
npm install
npm run dev
```

## Docker 部署

启动全部服务：

```bash
docker compose up -d --build
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

停止但保留数据：

```bash
docker compose down
```

停止并删除 PostgreSQL、Redis、MinIO、Qdrant 持久化数据：

```bash
docker compose down -v
```

## 知识库入库

当前检索链路：

```text
dense 向量检索 + BM25 sparse 检索
→ Qdrant RRF 融合
→ SiliconFlow Rerank
→ DeepSeek LLM 生成回答
```

首次部署、切换 Qdrant schema、清空知识库、或旧数据缺少 `company_id` 时，需要重建 Qdrant collection 并重新入库。

本地入库前请先停止后端，避免 embedded Qdrant 文件被占用：

```powershell
cd D:\AI_Projects\food-safety-assistant
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONPATH="D:\AI_Projects\food-safety-assistant\backend"
python -m scripts.ingest --recreate --company-id 1
```

Docker 入库：

```bash
docker compose exec backend python -m scripts.ingest \
  --kb-root /app/knowledge_base \
  --recreate \
  --company-id 1
```

只预览切分，不写入：

```bash
python -m scripts.ingest --dry-run --company-id 1
```

Docker 使用宿主知识库目录：

```bash
KB_PATH=/opt/food-safety/knowledge_base
DATA_PATH=/opt/food-safety/data
```

目录结构需要包含：

```text
knowledge_base/
  faq/
  manual/
```

## 多租户

默认租户：

```text
company_id=1
```

前端会把公司 ID 写入请求头 `X-Company-Id`，后端所有知识库、RAG、工单、反馈、会话、链路追踪都会按 `company_id` 隔离。Qdrant payload 也会写入并过滤 `company_id`。

给其他租户入库：

```bash
python -m scripts.ingest --recreate --company-id 2
```

注意：`--recreate` 会重建整个 collection。如果需要多个租户共存，不要对第二个租户使用 `--recreate`，改用：

```bash
python -m scripts.ingest --company-id 2
```

## 排查

健康检查：

```bash
curl http://localhost:5002/health
```

API 文档：

```text
http://localhost:5002/docs
```

前端报错时，复制界面上的 `Trace ID`，进入：

```text
管理后台 → 链路追踪
```

可以查看：

- 输入安全检查
- 意图识别
- dense + BM25 hybrid 检索
- rerank
- 置信度判断
- LLM 调用参数、响应摘要、token usage、耗时
- API 响应或异常详情

## 常见问题

### Dense vector is not found in the collection

说明 Qdrant collection 仍是旧 schema，缺少命名向量 `dense` 或 sparse 向量 `bm25`。停止后端后重新入库：

```bash
python -m scripts.ingest --recreate --company-id 1
```

### 前端提示系统处理时间较长

前端 axios 和 Docker Nginx 超时均为 180 秒。到管理后台用 Trace ID 查看具体慢在哪个节点，常见慢点是 `llm_call`。

### 切换 LLM 是否需要重新入库

不需要。重新入库只和 embedding 模型、Qdrant schema、知识库内容或 `company_id` payload 有关。
