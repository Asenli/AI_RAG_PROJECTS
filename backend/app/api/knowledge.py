"""Knowledge base management API router."""
import re
import hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from app.services.vector_store import vector_store
from app.services.embedding_svc import embedding_service
from app.services.sparse_embedding_svc import sparse_embedding_service
from app.services.knowledge_guard import KnowledgeGuard
from app.core.rag_engine import rag_engine
from app.config import settings
from app.services.chunking import split_text_by_tokens, token_count

router = APIRouter()

# In-memory document registry (production: PostgreSQL table)
doc_registry: dict = {}
DEFAULT_COMPANY_ID = settings.default_company_id


class SplitPreviewRequest(BaseModel):
    content: str
    knowledge_type: str = "faq"
    module: str = ""
    sub_module: str = ""
    company_id: str = DEFAULT_COMPANY_ID


def _split_long_chunks(chunks: list[dict]) -> list[dict]:
    split_chunks = []
    for chunk in chunks:
        parts = split_text_by_tokens(chunk["text"])
        if len(parts) == 1:
            if "metadata" in chunk:
                chunk["metadata"]["chunk_index"] = len(split_chunks)
                chunk["metadata"]["chunk_tokens"] = token_count(parts[0])
            split_chunks.append(chunk)
            continue
        for part_index, part in enumerate(parts):
            if "metadata" in chunk:
                metadata = dict(chunk["metadata"])
                metadata["parent_chunk_index"] = chunk["metadata"].get("chunk_index", 0)
                metadata["chunk_part"] = part_index + 1
                metadata["chunk_parts"] = len(parts)
                metadata["chunk_index"] = len(split_chunks)
                metadata["chunk_tokens"] = token_count(part)
                metadata["header_path"] = (
                    f"{metadata.get('header_path', '')}（片段 {part_index + 1}/{len(parts)}）"
                )
                split_chunks.append({"text": part, "metadata": metadata})
            else:
                header = chunk.get("header", "")
                split_chunks.append({
                    "text": part,
                    "header": f"{header}（片段 {part_index + 1}/{len(parts)}）",
                })
    return split_chunks


def _extract_header_info(text: str) -> dict:
    match = re.search(r"所属模块[：:]\s*(.+?)(?:\||$)", text)
    if not match:
        return {"module": "", "sub_module": ""}
    parts = [p.strip() for p in match.group(1).split(">")]
    return {
        "module": parts[0] if len(parts) > 0 else "",
        "sub_module": parts[1] if len(parts) > 1 else "",
    }


def _extract_role(text: str, default_role: str = "all") -> str:
    match = re.search(r"\*\*适用角色\*\*[：:]\s*(.+)", text)
    return match.group(1).strip() if match else default_role


def _chunk_markdown(content: str, knowledge_type: str) -> list[dict]:
    """Chunk Markdown by type."""
    chunks = []
    if knowledge_type == "faq":
        pattern = (
            r"(?:^|\n)(?:Q[：:]|##\s*(?:Q|问题|问))(.*?)"
            r"(?=(?:\n(?:Q[：:]|##\s*(?:Q|问题|问))|\Z))"
        )
        matches = re.findall(pattern, content, re.DOTALL)
        if not matches:
            parts = content.split("\n\n")
            chunks = [
                {"text": p.strip(), "header": ""}
                for p in parts if len(p.strip()) >= 10
            ]
        else:
            for m in matches:
                text = m.strip()
                if len(text) >= 10:
                    chunks.append({"text": text, "header": text[:50]})
    else:
        sections = re.split(r"\n(?=##\s)", content)
        for section in sections:
            header_match = re.match(r"##\s*(.+)", section)
            header = header_match.group(1).strip() if header_match else ""
            text = section.strip()
            if len(text) >= 20:
                chunks.append({"text": text, "header": header})

    if not chunks:
        chunks = [{"text": content.strip(), "header": ""}]
    return _split_long_chunks(chunks)


def _source_path(filename: str, module: str, knowledge_type: str) -> str:
    clean_type = (knowledge_type or "faq").strip()
    clean_module = (module or "未分类").strip()
    return f"{clean_type}/{clean_module}/{filename}"


def _build_ingest_chunks(
    content: str,
    filename: str,
    module: str,
    sub_module: str,
    knowledge_type: str,
    role: str,
    company_id: str,
) -> list[dict]:
    """Build chunks using the same payload shape as scripts.ingest."""
    source = _source_path(filename, module, knowledge_type)
    doc_info = _extract_header_info(content)
    module = module or doc_info.get("module", "")
    sub_module = sub_module or doc_info.get("sub_module", "")
    doc_role = _extract_role(content, role or "all")
    version = datetime.utcnow().strftime("%Y-%m-%d")

    chunks = []
    if knowledge_type == "faq":
        qa_sections = re.split(r"(?=^## Q\d+:)", content, flags=re.MULTILINE)
        for section in qa_sections:
            if not re.match(r"^## Q\d+:", section):
                continue
            title_match = re.match(r"^## Q\d+:\s*(.+)", section)
            question_title = title_match.group(1).strip() if title_match else section[:50]
            chunk_role = _extract_role(section, doc_role)
            chunks.append({
                "text": section.strip(),
                "metadata": {
                    "company_id": str(company_id),
                    "module": module,
                    "sub_module": sub_module,
                    "knowledge_type": knowledge_type,
                    "role": chunk_role,
                    "source": source,
                    "header_path": f"FAQ > {question_title}",
                    "priority": 1.0,
                    "version": version,
                    "chunk_index": len(chunks),
                    "upload_channel": "manual_upload",
                },
            })

    if not chunks and knowledge_type in {"manual", "system", "regulation"}:
        sections = re.split(r"(?=^### \d+\.\s)", content, flags=re.MULTILINE)
        for section in sections:
            if not re.match(r"^### \d+\.\s", section):
                continue
            title_match = re.match(r"^### \d+\.\s*(.+)", section)
            section_title = title_match.group(1).strip() if title_match else section[:50]
            chunks.append({
                "text": section.strip(),
                "metadata": {
                    "company_id": str(company_id),
                    "module": module,
                    "sub_module": sub_module,
                    "knowledge_type": knowledge_type,
                    "role": _extract_role(section, role or "all"),
                    "source": source,
                    "header_path": f"操作手册 > {section_title}",
                    "priority": 1.0,
                    "version": version,
                    "chunk_index": len(chunks),
                    "upload_channel": "manual_upload",
                },
            })

    if not chunks:
        fallback_chunks = _chunk_markdown(content, knowledge_type)
        for chunk in fallback_chunks:
            chunks.append({
                "text": chunk["text"],
                "metadata": {
                    "company_id": str(company_id),
                    "module": module,
                    "sub_module": sub_module,
                    "knowledge_type": knowledge_type,
                    "role": role or doc_role or "all",
                    "source": source,
                    "header_path": chunk.get("header", "") or filename,
                    "priority": 1.0,
                    "version": version,
                    "chunk_index": len(chunks),
                    "upload_channel": "manual_upload",
                },
            })

    return _split_long_chunks(chunks)


@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    module: str = Form(""),
    sub_module: str = Form(""),
    knowledge_type: str = Form("faq"),
    role: str = Form("all"),
    company_id: str = Form(DEFAULT_COMPANY_ID),
):
    if not file.filename or not file.filename.lower().endswith((".md", ".markdown")):
        raise HTTPException(400, "仅支持 Markdown (.md/.markdown) 文件")

    content = (await file.read()).decode("utf-8")
    validation = KnowledgeGuard.validate(content, file.filename)
    if not validation["valid"]:
        raise HTTPException(400, validation["reason"])

    company_id = str(company_id or DEFAULT_COMPANY_ID)
    chunks = _build_ingest_chunks(
        content=content,
        filename=file.filename,
        module=module,
        sub_module=sub_module,
        knowledge_type=knowledge_type,
        role=role,
        company_id=company_id,
    )
    if not chunks:
        raise HTTPException(400, "文档无法切分，请检查内容格式")

    texts = [c["text"] for c in chunks]
    try:
        vectors = await embedding_service.embed_documents(texts)
    except Exception as e:
        raise HTTPException(500, f"Embedding 生成失败: {str(e)}")

    try:
        sparse_vectors = sparse_embedding_service.embed_documents(texts)
    except Exception as e:
        raise HTTPException(500, f"BM25 向量生成失败: {str(e)}")

    metadata_list = []
    for chunk in chunks:
        metadata = dict(chunk["metadata"])
        metadata["text"] = chunk["text"][:4096]
        metadata_list.append(metadata)

    source_path = metadata_list[0]["source"]

    # Replace same source atomically at document level to avoid stale chunks.
    try:
        vector_store.delete_by_source(source_path, company_id=company_id)
    except Exception:
        pass
    vector_store.insert(vectors, sparse_vectors, metadata_list)

    doc_id = hashlib.md5(
        f"{company_id}:{source_path}".encode("utf-8")
    ).hexdigest()[:12]
    doc_registry[doc_id] = {
        "id": doc_id, "company_id": str(company_id),
        "filename": file.filename, "module": module,
        "sub_module": sub_module, "knowledge_type": knowledge_type,
        "role": role, "chunks": len(chunks), "md5": validation.get("md5", ""),
        "source": source_path, "status": "active", "managed": True,
        "version": metadata_list[0].get("version", ""),
    }

    return {
        "status": "ok", "doc_id": doc_id, "chunks": len(chunks),
        "filename": file.filename, "module": module, "company_id": str(company_id),
        "source": source_path,
    }


@router.get("/list")
async def list_knowledge(company_id: str = Query(DEFAULT_COMPANY_ID)):
    company_id = str(company_id)
    source_stats = vector_store.list_source_stats(company_id=company_id)
    sources = [item["source"] for item in source_stats]
    registry_docs = [
        doc for doc in doc_registry.values()
        if str(doc.get("company_id", DEFAULT_COMPANY_ID)) == company_id
    ]
    registered_sources = set()
    for doc in registry_docs:
        registered_sources.add(doc.get("source") or _source_path(
            doc["filename"],
            doc.get("module", ""),
            doc.get("knowledge_type", "faq"),
        ))

    source_docs = []
    for stat in source_stats:
        source = stat["source"]
        if source in registered_sources:
            continue
        parts = source.split("/")
        knowledge_type = stat.get("knowledge_type") or (parts[0] if len(parts) >= 1 else "")
        module = stat.get("module") or (parts[1] if len(parts) >= 2 else "")
        filename = parts[-1] if parts else source
        sub_module = (
            stat.get("sub_module")
            or filename.replace("FAQ.md", "")
            .replace("操作手册.md", "")
            .replace(".md", "")
        )
        managed = stat.get("upload_channel") == "manual_upload"
        source_docs.append({
            "id": f"source:{source}",
            "company_id": company_id,
            "filename": filename,
            "module": module,
            "sub_module": sub_module,
            "knowledge_type": knowledge_type,
            "role": stat.get("role", "all"),
            "chunks": stat.get("chunks", 0),
            "source": source,
            "status": "active",
            "managed": managed,
            "version": stat.get("version", ""),
            "upload_channel": stat.get("upload_channel", ""),
        })

    return {
        "company_id": company_id,
        "documents": registry_docs + source_docs,
        "total_documents": len(registry_docs) + len(source_docs),
        "total_chunks": vector_store.count(company_id=company_id),
        "sources": sources,
    }


@router.get("/detail")
async def knowledge_detail(
    source: str = Query(...),
    company_id: str = Query(DEFAULT_COMPANY_ID),
):
    company_id = str(company_id)
    chunks = vector_store.get_by_source(source, company_id=company_id)
    if not chunks:
        raise HTTPException(404, "文档不存在或没有可查看内容")

    first = chunks[0]
    filename = source.split("/")[-1]
    return {
        "company_id": company_id,
        "source": source,
        "filename": filename,
        "module": first.get("module", ""),
        "sub_module": first.get("sub_module", ""),
        "knowledge_type": first.get("knowledge_type", ""),
        "role": first.get("role", "all"),
        "version": first.get("version", ""),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "content": "\n\n---\n\n".join(chunk.get("text", "") for chunk in chunks),
    }


@router.post("/preview-split")
async def preview_split(req: SplitPreviewRequest):
    chunks = _build_ingest_chunks(
        content=req.content,
        filename="preview.md",
        module=req.module,
        sub_module=req.sub_module,
        knowledge_type=req.knowledge_type,
        role="all",
        company_id=req.company_id,
    )
    return {
        "total_chunks": len(chunks),
        "chunks": [
            {
                "index": i,
                "header": c.get("metadata", {}).get("header_path", ""),
                "text_preview": c["text"][:200],
                "text": c["text"],
                "metadata": c.get("metadata", {}),
                "length": len(c["text"]),
            }
            for i, c in enumerate(chunks)
        ],
    }


@router.get("/search-test")
async def search_test(
    q: str = Query(...),
    role: str = Query("school"),
    top_k: int = Query(10),
    company_id: str = Query(DEFAULT_COMPANY_ID),
):
    report = await rag_engine.search_test(q, role, top_k, str(company_id))
    return {
        **report,
        "company_id": str(company_id),
        "query": q,
        "role": role,
    }


@router.delete("/delete")
async def delete_knowledge_by_source(
    source: str = Query(...),
    company_id: str = Query(DEFAULT_COMPANY_ID),
):
    company_id = str(company_id)
    chunks = vector_store.get_by_source(source, company_id=company_id)
    if not chunks:
        raise HTTPException(404, "文档不存在")
    vector_store.delete_by_source(source, company_id=company_id)
    for doc_id, doc in list(doc_registry.items()):
        if (
            str(doc.get("company_id", DEFAULT_COMPANY_ID)) == company_id
            and doc.get("source") == source
        ):
            doc_registry.pop(doc_id, None)
    return {
        "status": "deleted",
        "company_id": company_id,
        "source": source,
        "deleted_chunks": len(chunks),
    }


@router.post("/reindex")
async def reindex_knowledge_by_source(
    source: str = Query(...),
    company_id: str = Query(DEFAULT_COMPANY_ID),
):
    company_id = str(company_id)
    chunks = vector_store.get_by_source(source, company_id=company_id)
    if not chunks:
        raise HTTPException(404, "文档不存在")

    texts = [chunk.get("text", "") for chunk in chunks if chunk.get("text")]
    if not texts:
        raise HTTPException(400, "文档没有可重建的文本内容")

    try:
        vectors = await embedding_service.embed_documents(texts)
        sparse_vectors = sparse_embedding_service.embed_documents(texts)
    except Exception as e:
        raise HTTPException(500, f"索引重建失败: {str(e)}")

    metadata_list = []
    for index, chunk in enumerate(chunks):
        metadata_list.append({
            "company_id": company_id,
            "text": chunk.get("text", "")[:4096],
            "module": chunk.get("module", ""),
            "sub_module": chunk.get("sub_module", ""),
            "knowledge_type": chunk.get("knowledge_type", ""),
            "role": chunk.get("role", "all"),
            "source": source,
            "header_path": chunk.get("header_path", ""),
            "priority": chunk.get("priority", 1.0),
            "version": chunk.get("version", ""),
            "chunk_index": index,
            "chunk_part": chunk.get("chunk_part"),
            "chunk_parts": chunk.get("chunk_parts"),
            "upload_channel": chunk.get("upload_channel", ""),
        })

    vector_store.delete_by_source(source, company_id=company_id)
    vector_store.insert(vectors, sparse_vectors, metadata_list)
    return {
        "status": "ok",
        "company_id": company_id,
        "source": source,
        "chunks": len(metadata_list),
    }


@router.delete("/{doc_id}")
async def delete_knowledge(
    doc_id: str,
    company_id: str = Query(DEFAULT_COMPANY_ID),
):
    if doc_id not in doc_registry:
        raise HTTPException(404, "文档不存在")
    info = doc_registry.pop(doc_id)
    source = info.get("source") or _source_path(
        info["filename"],
        info.get("module", ""),
        info.get("knowledge_type", "faq"),
    )
    try:
        vector_store.delete_by_source(source, company_id=str(company_id))
    except Exception:
        pass
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/{doc_id}/reindex")
async def reindex_knowledge(doc_id: str):
    if doc_id not in doc_registry:
        raise HTTPException(404, "文档不存在")
    info = doc_registry[doc_id]
    return {
        "status": "queued", "doc_id": doc_id,
        "source": info.get("source", ""),
        "message": "请调用 /knowledge/reindex?source=... 执行即时重建索引",
    }
