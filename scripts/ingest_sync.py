#!/usr/bin/env python3
"""Standalone sync ingest — 同步调用 SiliconFlow API + HF 镜像。"""
import os, sys, re, time, hashlib, json

# HuggingFace 国内镜像（必须在 import fastembed 之前设置）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition,
    MatchValue, SparseVector, SparseVectorParams, Modifier, SparseIndexParams,
)
from fastembed import SparseTextEmbedding
from app.config import settings
from app.services.chunking import split_text_by_tokens, token_count

# ── 配置 ──
KB_ROOT = os.path.join(os.path.dirname(__file__), "..", "knowledge_base")
BATCH_SIZE = 16
COLLECTION = settings.qdrant_collection
DIMENSION = 1024
DENSE_NAME = "dense"
SPARSE_NAME = "bm25"

ROLE_MAP = {
    "education_bureau": "education_bureau", "school": "school",
    "canteen": "canteen", "distributor": "distributor",
    "purchaser": "purchaser", "storekeeper": "storekeeper",
    "finance": "finance", "cashier": "cashier",
    "inspector": "inspector", "nutritionist": "nutritionist", "admin": "admin",
}


def chunk_faq(text, file_meta):
    chunks = []
    doc_info = extract_header_info(text)
    first_role = extract_role(text)
    qa_sections = re.split(r"(?=^## Q\d+:)", text, flags=re.MULTILINE)
    for section in qa_sections:
        if not re.match(r"^## Q\d+:", section):
            continue
        title_match = re.match(r"^## Q\d+:\s*(.+)", section)
        question_title = title_match.group(1).strip() if title_match else ""
        role = extract_role(section)
        if role == "all":
            role = first_role
        chunks.append({
            "text": section.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", "1"),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "faq",
                "role": role,
                "source": file_meta["source"],
                "header_path": f"FAQ > {question_title}",
                "priority": 1.0,
                "version": "2026-08-11",
                "chunk_index": len(chunks),
            },
        })
    return chunks


def chunk_manual(text, file_meta):
    chunks = []
    doc_info = extract_header_info(text)
    sections = re.split(r"(?=^### \d+\.\s)", text, flags=re.MULTILINE)
    for section in sections:
        if not re.match(r"^### \d+\.\s", section):
            continue
        title_match = re.match(r"^### \d+\.\s*(.+)", section)
        section_title = title_match.group(1).strip() if title_match else ""
        role = extract_role(section)
        if role == "all":
            role_match = re.search(r"\*\*适用角色\*\*[：:]\s*(\S+)", section)
            if role_match:
                role = ROLE_MAP.get(role_match.group(1).strip(), "all")
        chunks.append({
            "text": section.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", "1"),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "manual",
                "role": role,
                "source": file_meta["source"],
                "header_path": f"操作手册 > {section_title}",
                "priority": 1.0,
                "version": "2026-08-11",
                "chunk_index": len(chunks),
            },
        })
    if not chunks:
        chunks.append({
            "text": text.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", "1"),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "manual",
                "role": "all",
                "source": file_meta["source"],
                "header_path": "操作手册 > 概述",
                "priority": 1.0,
                "version": "2026-08-11",
                "chunk_index": 0,
            },
        })
    return chunks


def split_long_chunks(chunks):
    split_chunks = []
    for chunk in chunks:
        text = chunk["text"].strip()
        parts = split_text_by_tokens(text)
        if len(parts) == 1:
            chunk["metadata"]["chunk_index"] = len(split_chunks)
            chunk["metadata"]["chunk_tokens"] = token_count(parts[0])
            split_chunks.append(chunk)
            continue
        for pi, part in enumerate(parts):
            meta = dict(chunk["metadata"])
            meta["parent_chunk_index"] = chunk["metadata"].get("chunk_index", 0)
            meta["chunk_part"] = pi + 1
            meta["chunk_parts"] = len(parts)
            meta["chunk_index"] = len(split_chunks)
            meta["chunk_tokens"] = token_count(part)
            meta["header_path"] = f"{meta.get('header_path', '')}（片段 {pi+1}/{len(parts)}）"
            split_chunks.append({"text": part, "metadata": meta})
    return split_chunks


def extract_header_info(text):
    m = re.search(r"所属模块[：:]\s*(.+?)(?:\||$)", text)
    if m:
        parts = [p.strip() for p in m.group(1).split(">")]
        return {"module": parts[0] if parts else "", "sub_module": parts[1] if len(parts) > 1 else ""}
    return {"module": "", "sub_module": ""}


def extract_role(text):
    m = re.search(r"\*\*适用角色\*\*[：:]\s*(.+)", text)
    if m:
        role = m.group(1).strip()
        return ROLE_MAP.get(role, role)
    return "all"


def walk_kb(root):
    all_chunks = []
    fc = 0
    for ktype in ["faq", "manual"]:
        ktype_dir = os.path.join(root, ktype)
        if not os.path.isdir(ktype_dir):
            continue
        for module_dir in sorted(os.listdir(ktype_dir)):
            module_path = os.path.join(ktype_dir, module_dir)
            if not os.path.isdir(module_path):
                continue
            for fn in sorted(os.listdir(module_path)):
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(module_path, fn)
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
                sub_name = fn.replace("FAQ.md", "").replace("操作手册.md", "").replace(".md", "")
                if not sub_name:
                    sub_name = module_dir
                file_meta = {
                    "company_id": "1",
                    "module": module_dir,
                    "sub_module": sub_name,
                    "source": f"{ktype}/{module_dir}/{fn}",
                }
                if ktype == "faq":
                    chunks = chunk_faq(content, file_meta)
                else:
                    chunks = chunk_manual(content, file_meta)
                chunks = split_long_chunks(chunks)
                if chunks:
                    all_chunks.extend(chunks)
                    fc += 1
                    print(f"  📄 {ktype}/{module_dir}/{fn} → {len(chunks)} chunks")
    print(f"\n📊 总计: {fc} 个文件, {len(all_chunks)} 个 chunks")
    return all_chunks


def init_qdrant(recreate=False):
    db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "qdrant_data"))
    os.makedirs(db_dir, exist_ok=True)
    client = QdrantClient(path=db_dir)
    if recreate and client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
        print(f"♻️  已删除旧集合 {COLLECTION}")
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={DENSE_NAME: VectorParams(size=DIMENSION, distance=Distance.COSINE)},
            sparse_vectors_config={SPARSE_NAME: SparseVectorParams(modifier=Modifier.IDF)},
        )
        print(f"✅ 已创建 Hybrid 集合: {COLLECTION}")
    return client


def point_id(payload):
    key = "|".join([
        str(payload.get("company_id", "1")),
        str(payload.get("source", "")),
        str(payload.get("chunk_index", "")),
        str(payload.get("header_path", "")),
    ])
    digest = hashlib.sha1(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Standalone sync knowledge base ingestion")
    parser.add_argument("--recreate", action="store_true", help="Drop & recreate Qdrant collection")
    args = parser.parse_args()

    print(f"📂 知识库: {os.path.abspath(KB_ROOT)}")
    print(f"🔑 API Key: {settings.siliconflow_api_key[:20]}...")
    print()

    # 1. 切分
    chunks = walk_kb(KB_ROOT)
    if not chunks:
        print("⚠️ 无文档")
        return

    # 2. 初始化客户端
    ai = OpenAI(api_key=settings.siliconflow_api_key, base_url=settings.embedding_base_url, timeout=60)
    bm25 = SparseTextEmbedding(model_name="Qdrant/bm25")
    qdrant = init_qdrant(recreate=args.recreate)
    print(f"\n✅ Qdrant collection: {COLLECTION}")

    # 3. 逐 batch 入库
    total = len(chunks)
    inserted = 0
    print(f"\n🚀 开始入库 {total} 个文档片段...")

    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        metas = [dict(c["metadata"]) for c in batch]

        # Embed (同步 + 重试)
        for attempt in range(3):
            try:
                resp = ai.embeddings.create(model=settings.embedding_model, input=texts)
                vectors = [d.embedding for d in resp.data]
                break
            except Exception as e:
                if attempt < 2:
                    delay = 2 * (2 ** attempt)
                    print(f"  [重试] batch {i//BATCH_SIZE} 第{attempt+1}次失败: {e}，{delay}s 后重试...")
                    time.sleep(delay)
                else:
                    raise

        # BM25 稀疏向量
        sparse_vectors = list(bm25.embed(texts))

        # 构建 payload + 写入
        payloads = []
        for text, meta in zip(texts, metas):
            p = dict(meta)
            p["text"] = text[:4096]
            p["company_id"] = str(p.get("company_id", "1"))
            payloads.append(p)

        points = []
        for vec, sv, pl in zip(vectors, sparse_vectors, payloads):
            sv_obj = SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
            uid = point_id(pl)
            points.append(PointStruct(
                id=uid,
                vector={DENSE_NAME: vec, SPARSE_NAME: sv_obj},
                payload=pl,
            ))

        qdrant.upsert(collection_name=COLLECTION, points=points, wait=True)
        inserted += len(points)
        progress = min(i + BATCH_SIZE, total)
        print(f"  [{progress}/{total}] 已入库 {inserted} 条...")
        time.sleep(0.3)

    print(f"\n✅ 入库完成! 共 {inserted} 条")
    print(f"   Qdrant 总记录: {qdrant.count(COLLECTION, exact=True).count} 条")


if __name__ == "__main__":
    main()
