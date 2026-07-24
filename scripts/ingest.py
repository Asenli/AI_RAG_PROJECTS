#!/usr/bin/env python3
"""
Knowledge base ingestion script.

Reads Markdown knowledge base files (faq/ and manual/), splits them into
semantic chunks, generates embeddings via SiliconFlow API, and inserts into
Qdrant vector store with dense + BM25 sparse vectors for hybrid retrieval.

Usage:
    python -m scripts.ingest --company-id 1
    python -m scripts.ingest --recreate --company-id 1
    python -m scripts.ingest --dry-run --company-id 1
    python -m scripts.ingest --module 食堂管理  # Ingest single module
"""
import os
import re
import sys
import time
import argparse
import asyncio
from pathlib import Path

# Add parent directory to path for imports
# Works both locally (scripts/ alongside backend/) and in Docker (scripts/ inside /app/)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_script_dir)
sys.path.insert(0, _parent)
# Also try one level up for local dev (scripts/ is alongside backend/)
if os.path.isdir(os.path.join(_parent, "backend")):
    sys.path.insert(0, os.path.join(_parent, "backend"))

from app.services.embedding_svc import embedding_service
from app.services.sparse_embedding_svc import sparse_embedding_service
from app.services.vector_store import vector_store
from app.config import settings

# ── Constants ──
KB_ROOT = os.environ.get("KB_ROOT", os.path.join(os.path.dirname(__file__), "..", "knowledge_base"))
BATCH_SIZE = 16  # SiliconFlow max batch size
MAX_EMBED_CHARS = 480  # Keep Chinese chunks under SiliconFlow embedding input limits.
DEFAULT_COMPANY_ID = os.environ.get("COMPANY_ID", settings.default_company_id)
ROLE_MAP = {
    "education_bureau": "education_bureau",
    "school": "school",
    "canteen": "canteen",
    "distributor": "distributor",
    "purchaser": "purchaser",
    "storekeeper": "storekeeper",
    "finance": "finance",
    "cashier": "cashier",
    "inspector": "inspector",
    "nutritionist": "nutritionist",
    "admin": "admin",
}


def split_long_text(text: str, max_chars: int = MAX_EMBED_CHARS) -> list[str]:
    """Split long text into embedding-safe chunks, preferring paragraph breaks."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    parts = []
    current = ""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

    for block in blocks:
        if len(block) > max_chars:
            if current:
                parts.append(current.strip())
                current = ""
            for start in range(0, len(block), max_chars):
                parts.append(block[start : start + max_chars].strip())
            continue

        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current.strip())
            current = block

    if current:
        parts.append(current.strip())

    return [p for p in parts if p]


def split_long_chunks(chunks: list[dict]) -> list[dict]:
    """Split chunks that are too long for the embedding API."""
    split_chunks = []

    for chunk in chunks:
        text = chunk["text"].strip()
        parts = split_long_text(text)
        if len(parts) == 1:
            chunk["metadata"]["chunk_index"] = len(split_chunks)
            split_chunks.append(chunk)
            continue

        for part_index, part in enumerate(parts):
            metadata = dict(chunk["metadata"])
            metadata["parent_chunk_index"] = chunk["metadata"].get("chunk_index", 0)
            metadata["chunk_part"] = part_index + 1
            metadata["chunk_parts"] = len(parts)
            metadata["chunk_index"] = len(split_chunks)
            metadata["header_path"] = (
                f"{metadata.get('header_path', '')}（片段 {part_index + 1}/{len(parts)}）"
            )
            split_chunks.append({"text": part, "metadata": metadata})

    return split_chunks


def extract_header_info(text: str) -> dict:
    """Extract module/sub_module from '> 所属模块：xxx > yyy' metadata line."""
    match = re.search(r"所属模块[：:]\s*(.+?)(?:\||$)", text)
    if match:
        parts = [p.strip() for p in match.group(1).split(">")]
        module = parts[0] if len(parts) > 0 else ""
        sub_module = parts[1] if len(parts) > 1 else ""
        return {"module": module, "sub_module": sub_module}
    return {"module": "", "sub_module": ""}


def extract_role(text: str) -> str:
    """Extract role from '**适用角色**: xxx' line."""
    match = re.search(r"\*\*适用角色\*\*[：:]\s*(.+)", text)
    if match:
        role = match.group(1).strip()
        return ROLE_MAP.get(role, role)
    return "all"


def extract_difficulty(text: str) -> str:
    """Extract difficulty from '**难度**: xxx' line."""
    match = re.search(r"\*\*难度\*\*[：:]\s*(\w+)", text)
    return match.group(1) if match else "medium"


def chunk_faq(text: str, file_meta: dict) -> list[dict]:
    """Split FAQ document by Q&A pairs (## QN: ... sections)."""
    chunks = []

    # Extract the overall document metadata
    doc_info = extract_header_info(text)
    first_role = extract_role(text)

    # Split by ## Q\d+: headers
    qa_sections = re.split(r"(?=^## Q\d+:)", text, flags=re.MULTILINE)

    for section in qa_sections:
        # Skip preamble (before first Q)
        if not re.match(r"^## Q\d+:", section):
            continue

        # Extract question title
        title_match = re.match(r"^## Q\d+:\s*(.+)", section)
        question_title = title_match.group(1).strip() if title_match else ""

        # Extract metadata from this Q&A
        role = extract_role(section)
        if role == "all":
            role = first_role  # Fall back to doc-level role

        difficulty = extract_difficulty(section)

        chunks.append({
            "text": section.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", DEFAULT_COMPANY_ID),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "faq",
                "role": role,
                "source": file_meta.get("source", ""),
                "header_path": f"FAQ > {question_title}",
                "priority": 1.0,
                "version": "2026-06-30",
                "chunk_index": len(chunks),
            },
        })

    return chunks


def chunk_manual(text: str, file_meta: dict) -> list[dict]:
    """Split Manual document by ### section headers."""
    chunks = []

    doc_info = extract_header_info(text)

    # Split by ### N. headers
    sections = re.split(r"(?=^### \d+\.\s)", text, flags=re.MULTILINE)

    for section in sections:
        # Skip preamble/overview/注意事项
        if not re.match(r"^### \d+\.\s", section):
            continue

        # Extract section title
        title_match = re.match(r"^### \d+\.\s*(.+)", section)
        section_title = title_match.group(1).strip() if title_match else ""

        role = extract_role(section)
        if role == "all":
            # Try to find role from the section
            role_match = re.search(r"\*\*适用角色\*\*[：:]\s*(\S+)", section)
            if role_match:
                role = ROLE_MAP.get(role_match.group(1).strip(), "all")

        chunks.append({
            "text": section.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", DEFAULT_COMPANY_ID),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "manual",
                "role": role,
                "source": file_meta.get("source", ""),
                "header_path": f"操作手册 > {section_title}",
                "priority": 1.0,
                "version": "2026-06-30",
                "chunk_index": len(chunks),
            },
        })

    # If no ### sections found, treat whole doc as one chunk
    if not chunks:
        chunks.append({
            "text": text.strip(),
            "metadata": {
                "company_id": file_meta.get("company_id", DEFAULT_COMPANY_ID),
                "module": file_meta.get("module", doc_info.get("module", "")),
                "sub_module": file_meta.get("sub_module", doc_info.get("sub_module", "")),
                "knowledge_type": "manual",
                "role": "all",
                "source": file_meta.get("source", ""),
                "header_path": "操作手册 > 概述",
                "priority": 1.0,
                "version": "2026-06-30",
                "chunk_index": 0,
            },
        })

    return chunks


def walk_knowledge_base(
    root: str = None,
    target_module: str = None,
    company_id: str = DEFAULT_COMPANY_ID,
) -> list[dict]:
    """Walk knowledge_base directory and parse all Markdown files."""
    if root is None:
        root = KB_ROOT

    all_chunks = []
    file_count = 0

    for ktype in ["faq", "manual"]:
        ktype_dir = os.path.join(root, ktype)
        if not os.path.isdir(ktype_dir):
            continue

        for module_dir in sorted(os.listdir(ktype_dir)):
            module_path = os.path.join(ktype_dir, module_dir)
            if not os.path.isdir(module_path):
                continue

            # Filter by module if specified
            if target_module and module_dir != target_module:
                continue

            for filename in sorted(os.listdir(module_path)):
                if not filename.endswith(".md"):
                    continue

                filepath = os.path.join(module_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    print(f"  ⚠️  读取失败: {filepath} — {e}")
                    continue

                # Extract sub_module from filename
                sub_name = filename.replace("FAQ.md", "").replace("操作手册.md", "").replace(".md", "")
                if not sub_name:
                    sub_name = module_dir

                file_meta = {
                    "company_id": company_id,
                    "module": module_dir,
                    "sub_module": sub_name,
                    "source": f"{ktype}/{module_dir}/{filename}",
                }

                # Chunk by knowledge type
                if ktype == "faq":
                    chunks = chunk_faq(content, file_meta)
                else:
                    chunks = chunk_manual(content, file_meta)

                chunks = split_long_chunks(chunks)

                if chunks:
                    all_chunks.extend(chunks)
                    file_count += 1
                    print(f"  📄 {ktype}/{module_dir}/{filename} → {len(chunks)} chunks")

    print(f"\n📊 总计: {file_count} 个文件, {len(all_chunks)} 个 chunks")
    return all_chunks


async def ingest_batch(texts: list[str], metadatas: list[dict]) -> int:
    """Embed a batch of texts and insert into Qdrant."""
    # Get dense semantic embeddings and sparse BM25 vectors.
    embeddings = await embedding_service.embed_documents(texts)
    sparse_embeddings = sparse_embedding_service.embed_documents(texts)
    payloads = []
    for text, metadata in zip(texts, metadatas):
        payload = dict(metadata)
        payload["text"] = text[:4096]
        payloads.append(payload)

    # Insert into Qdrant
    result = vector_store.insert(embeddings, sparse_embeddings, payloads)
    return result.get("insert_count", len(texts))


async def ingest_all(chunks: list[dict], dry_run: bool = False) -> int:
    """Ingest all chunks into Qdrant."""
    if dry_run:
        print("\n🔍 [Dry Run] 切分预览:")
        for i, chunk in enumerate(chunks[:10]):
            print(f"\n  Chunk {i}:")
            print(f"    module={chunk['metadata']['module']}")
            print(f"    sub_module={chunk['metadata']['sub_module']}")
            print(f"    type={chunk['metadata']['knowledge_type']}")
            print(f"    role={chunk['metadata']['role']}")
            print(f"    source={chunk['metadata']['source']}")
            print(f"    text_preview={chunk['text'][:100]}...")
        if len(chunks) > 10:
            print(f"\n  ... 还有 {len(chunks) - 10} 个 chunks")
        return 0

    total = len(chunks)
    inserted = 0

    print(f"\n🚀 开始入库 {total} 个文档片段...")
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        try:
            count = await ingest_batch(texts, metadatas)
            inserted += count
            progress = min(i + BATCH_SIZE, total)
            print(f"  [{progress}/{total}] 已入库 {inserted} 条...")
            time.sleep(0.5)  # Rate limit
        except Exception as e:
            print(f"  ⚠️  Batch {i // BATCH_SIZE} 入库失败: {e}")
            print("     正在降级为逐条入库以定位异常文档...")
            for chunk in batch:
                try:
                    count = await ingest_batch([chunk["text"]], [chunk["metadata"]])
                    inserted += count
                except Exception as item_error:
                    meta = chunk["metadata"]
                    print(
                        "     跳过: "
                        f"{meta.get('source', '')} | {meta.get('header_path', '')} "
                        f"| length={len(chunk['text'])} | error={str(item_error)[:160]}"
                    )
                time.sleep(0.5)
            print(f"  [{min(i + BATCH_SIZE, total)}/{total}] 已入库 {inserted} 条...")

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Knowledge base ingestion")
    parser.add_argument("--dry-run", action="store_true", help="Preview chunking without embedding")
    parser.add_argument("--module", type=str, help="Ingest single module only")
    parser.add_argument("--kb-root", type=str, help="Knowledge base root directory")
    parser.add_argument(
        "--company-id",
        type=str,
        default=DEFAULT_COMPANY_ID,
        help="Company/tenant ID for all ingested chunks (default: 1)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate Qdrant collection with dense + BM25 schema before ingest",
    )
    args = parser.parse_args()

    kb_root = args.kb_root or KB_ROOT
    if not os.path.isdir(kb_root):
        print(f"❌ 知识库目录不存在: {kb_root}")
        print("   请设置 KB_ROOT 环境变量或确保 knowledge_base/ 目录存在")
        sys.exit(1)

    print(f"📂 知识库根目录: {kb_root}")
    print(f"🏢 公司/租户 company_id: {args.company_id}")
    print()

    # 1. Walk and parse
    chunks = walk_knowledge_base(kb_root, args.module, args.company_id)

    if not chunks:
        print("⚠️  没有找到知识库文档。请将 Markdown 文件放入 knowledge_base/faq/ 和 knowledge_base/manual/")
        return

    try:
        # 2. Ingest
        if args.recreate and not args.dry_run:
            print("♻️  重建 Qdrant collection: dense + BM25 hybrid schema")
            vector_store.recreate_collection()

        inserted = asyncio.run(ingest_all(chunks, dry_run=args.dry_run))

        if not args.dry_run:
            print(f"\n✅ 入库完成! 共入库 {inserted} 条文档")
            print(
                "   Qdrant collection: "
                f"{vector_store.count(company_id=args.company_id)} 条记录 "
                f"(company_id={args.company_id})"
            )
    finally:
        vector_store.close()


if __name__ == "__main__":
    main()
