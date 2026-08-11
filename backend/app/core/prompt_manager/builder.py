"""上下文组装器 — 将检索 chunks 组装为带元数据的结构化上下文字符串."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

BuildMode = Literal["standard", "citation", "compact"]


@dataclass
class ChunkMeta:
    """从 Qdrant 检索结果中提取的标准化元数据."""
    text: str = ""
    doc_title: str = ""
    section: str = ""
    page: str = ""
    source_url: str = ""
    chunk_index: int = 0
    module: str = ""
    knowledge_type: str = ""
    score: float = 0.0
    doc_id: int = 0

    @classmethod
    def from_qdrant_result(cls, result: dict) -> "ChunkMeta":
        """从 Qdrant 搜索结果中提取标准化元数据.

        兼容两种格式:
            格式A (原始 Qdrant): {"id": ..., "distance": ..., "entity": {payload}}
            格式B (rag_engine 内部): {"text": ..., "metadata": {...}, "final_score": ...}
        """
        if "entity" in result:
            entity = result["entity"]
            return cls(
                text=entity.get("text", ""),
                doc_title=entity.get("source", ""),
                section=entity.get("header_path", ""),
                module=entity.get("module", ""),
                knowledge_type=entity.get("knowledge_type", ""),
                chunk_index=entity.get("chunk_index", 0) or 0,
                score=result.get("distance", 0) or 0.0,
                doc_id=result.get("id", 0) or 0,
            )
        else:
            metadata = result.get("metadata", {})
            return cls(
                text=result.get("text", ""),
                doc_title=metadata.get("source", ""),
                section=metadata.get("header_path", ""),
                module=metadata.get("module", ""),
                knowledge_type=metadata.get("knowledge_type", ""),
                chunk_index=metadata.get("chunk_index", 0) or 0,
                page=str((metadata.get("chunk_index", 0) or 0) + 1),
                score=result.get("final_score", result.get("score", 0)) or 0.0,
                doc_id=result.get("id", 0) or 0,
            )


class ContextBuilder:
    """将检索结果组装为结构化的上下文字符串.

    三种组装模式:
        - standard: 标准格式，显示来源 + 章节 + 全文
        - citation:  引用格式，给每个 chunk 分配 [N]，末尾列出引用
        - compact:   精简格式，仅显示文本截断，适合上下文紧张
    """

    def __init__(self, settings=None):
        self._settings = settings

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build(
        self,
        chunks: list[dict],
        mode: BuildMode = "standard",
        max_chunks: Optional[int] = None,
    ) -> str:
        """主入口: 将 chunks 列表组装为上下文字符串.

        Args:
            chunks: Qdrant 检索结果列表
            mode: "standard" | "citation" | "compact"
            max_chunks: 最多使用多少个 chunk，None 表示全部

        Returns:
            组装好的上下文字符串
        """
        metas = [ChunkMeta.from_qdrant_result(c) for c in chunks]

        if max_chunks is not None:
            metas = metas[:max_chunks]

        builder_method = {
            "standard": self._build_standard,
            "citation": self._build_citation,
            "compact": self._build_compact,
        }.get(mode, self._build_standard)

        return builder_method(metas)

    # ------------------------------------------------------------------
    # 三种组装模式
    # ------------------------------------------------------------------

    def _build_standard(self, metas: list[ChunkMeta]) -> str:
        parts = []
        for i, m in enumerate(metas, 1):
            lines = [f"## 文档 {i}"]
            if m.doc_title:
                lines.append(f"- 来源: {m.doc_title}")
            if m.section:
                lines.append(f"- 章节: {m.section}")
            if m.module:
                lines.append(f"- 模块: {m.module}")
            if m.page:
                lines.append(f"- 页码: p{m.page}")
            lines.append("- 内容:")
            lines.append(m.text)
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def _build_citation(self, metas: list[ChunkMeta]) -> str:
        doc_parts = []
        ref_parts = []

        for i, m in enumerate(metas, 1):
            ref_label = f"[{i}]"
            meta_parts = [ref_label]
            if m.doc_title:
                meta_parts.append(f"《{m.doc_title}》")
            if m.section:
                meta_parts.append(m.section.lstrip("# "))
            if m.page:
                meta_parts.append(f"p{m.page}")
            meta_line = " | ".join(meta_parts)

            doc_parts.append(f"{meta_line}\n{m.text}")
            ref_parts.append(
                f"{ref_label} {m.doc_title}, {m.section}".rstrip(", ")
            )

        body = "\n\n".join(doc_parts)
        refs = "\n".join(ref_parts)
        return f"{body}\n\n---\n引用来源:\n{refs}"

    def _build_compact(self, metas: list[ChunkMeta]) -> str:
        lines = []
        for i, m in enumerate(metas, 1):
            short_title = self._short_title(m.doc_title)
            section_abbr = self._short_section(m.section)
            text_preview = m.text[:300]
            if len(m.text) > 300:
                text_preview += "..."
            lines.append(
                f"[源{i}] {short_title}{section_abbr}: {text_preview}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _short_title(title: str) -> str:
        if not title:
            return ""
        for suffix in [".pdf", ".md", ".txt", ".docx"]:
            title = title.removesuffix(suffix)
        if len(title) > 10:
            return title[:6] + "..."
        return title

    @staticmethod
    def _short_section(section: str) -> str:
        if not section:
            return ""
        m = re.match(r"第([一二三四五六七八九十\d]+)[章节条款]", section)
        if m:
            num = m.group(1)
            rest = section[m.end():].strip()
            return f"§{num} {rest[:8]}" if rest else f"§{num}"
        return section[:10]

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的路径分隔符."""
        return name.replace("/", "_").replace("\\", "_")
