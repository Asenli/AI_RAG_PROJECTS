"""安全过滤器 — 检索内容清洗 + XML 结构隔离 + System Prompt 泄露检测."""
from __future__ import annotations
import re
from typing import Optional


class SafetyFilter:
    """Prompt 安全过滤器.

    三层防护:
        1. 输入清洗: 过滤检索内容中的危险关键词
        2. 结构隔离: 用 XML 标签将检索内容与系统指令物理隔离
        3. 输出检测: 检测 LLM 回答中是否泄露了 System Prompt
    """

    # 危险注入模式（中英文）
    DANGER_PATTERNS: list[tuple[str, str]] = [
        (r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?", "注入:忽略指令"),
        (r"(?i)disregard\s+(all\s+)?(previous|above)\s+instructions?", "注入:无视指令"),
        (r"(?i)forget\s+(all\s+)?(previous|earlier)\s+instructions?", "注入:忘记指令"),
        (r"(?i)you\s+are\s+now\s+(a\s+)?DAN\b", "注入:DAN模式"),
        (r"(?i)developer\s*mode", "注入:开发者模式"),
        (r"(?i)jailbreak", "注入:越狱"),
        (r"(?i)(print|show|reveal|display|output|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions?)", "注入:提取指令"),
        (r"(?i)(what|who)\s+(are|is)\s+your\s+(initial\s+)?(prompt|instructions?)", "注入:询问指令"),
        (r"(?i)from\s+now\s+on\s+you\s+(are|will\s+be|must\s+act\s+as)", "注入:角色覆盖"),
        (r"(?i)you\s+are\s+no\s+longer", "注入:角色覆盖"),
        (r"忽略.*(上面|之前|前面|先前|以前的).*(指令|指示)", "注入:中文忽略指令"),
        (r"(输出|显示|打印|告诉我?|泄露).*(系统|你的).*(指令|提示|prompt)", "注入:中文提取指令"),
    ]

    # System Prompt 泄露检测模式
    LEAK_PATTERNS: list[tuple[str, str]] = [
        (r"不可变更", "可能泄露了安全规则"),
        (r"system\s*prompt", "直接提及 system prompt"),
        (r"系统指令", "直接提及系统指令"),
        (r"系统提示", "直接提及系统提示"),
        (r"售后智能助手.*职责.*帮助用户", "疑似泄露角色定义"),
    ]

    XML_WRAPPER_OPEN = "<retrieved_documents>"
    XML_WRAPPER_CLOSE = "</retrieved_documents>"

    def __init__(self, settings=None):
        self._enabled = True
        if settings is not None:
            self._enabled = getattr(settings, "safety_filter_enabled", True)

        # 编译正则
        self._danger_re = [
            (re.compile(pattern), label)
            for pattern, label in self.DANGER_PATTERNS
        ]
        self._leak_re = [
            (re.compile(pattern), label)
            for pattern, label in self.LEAK_PATTERNS
        ]

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def sanitize_documents(self, documents_text: str) -> tuple[str, list[str]]:
        """清洗检索文档内容中的危险注入.

        Returns:
            (清洗后文本, 检测到的威胁列表)
        """
        if not self._enabled:
            return documents_text, []

        threats = []
        cleaned = documents_text

        for regex, label in self._danger_re:
            if regex.search(cleaned):
                threats.append(label)
                cleaned = regex.sub(f"[内容已过滤:{label}]", cleaned)

        return cleaned, threats

    def wrap_documents(self, documents_text: str) -> str:
        """用 XML 标签包裹检索内容，实现结构隔离."""
        return f"{self.XML_WRAPPER_OPEN}\n{documents_text}\n{self.XML_WRAPPER_CLOSE}"

    def sanitize_messages(self, messages: list[dict]) -> list[dict]:
        """对完整 messages 列表做安全检查: 确保 system message 中的检索内容被 XML 包裹."""
        if not self._enabled:
            return messages

        for msg in messages:
            if msg.get("role") != "system":
                continue
            content = msg["content"]
            if self.XML_WRAPPER_OPEN not in content:
                content = self._insert_xml_wrapper(content)
            msg["content"] = content

        return messages

    def detect_leak(self, llm_response: str) -> Optional[str]:
        """检测 LLM 回答中是否泄露了 System Prompt.

        Returns:
            泄露描述字符串，未检测到则返回 None
        """
        if not self._enabled:
            return None

        for regex, label in self._leak_re:
            if regex.search(llm_response):
                return label
        return None

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _insert_xml_wrapper(self, content: str) -> str:
        """在检索内容前后插入 XML 包裹标签."""
        markers = [
            "## 知识库内容",
            "知识库内容",
            "## 检索到的文档",
            "检索到的文档",
            "## 参考资料",
        ]
        for marker in markers:
            idx = content.find(marker)
            if idx != -1:
                before = content[:idx + len(marker)]
                after = content[idx + len(marker):]
                return (
                    before
                    + f"\n{self.XML_WRAPPER_OPEN}\n{after.strip()}\n{self.XML_WRAPPER_CLOSE}"
                )

        return content + f"\n\n{self.XML_WRAPPER_OPEN}\n{self.XML_WRAPPER_CLOSE}"
