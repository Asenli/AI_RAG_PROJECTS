"""Intent classifier — rule-first intent detection for inbound questions.

Inserted after InputGuard and before Embedding, this classifier shortcuts
the full RAG pipeline when users explicitly request ticket creation.
"""
import asyncio
import re
from app.services.llm_svc import llm_service



class IntentClassifier:
    """Rule-first intent classifier with a short LLM fallback for fuzzy cases.

    The common path is local and fast:
    - explicit ticket/repair/complaint/manual-service phrases -> create_ticket
    - greetings/chitchat/tests -> other
    - regular business questions -> answer

    Only fuzzy "please handle it" style requests use the LLM, and that call is
    capped so intent detection cannot dominate the whole RAG latency.
    """

    TICKET_KEYWORDS = [
        "创建工单", "生成工单", "提交工单", "新建工单", "开工单", "建工单",
        "创建一个工单", "生成一个工单", "提交一个工单", "新建一个工单",
        "开一个工单", "建一个工单", "帮我开一个工单", "帮我创建一个工单",
        "报修", "投诉", "转人工", "人工客服", "人工处理", "联系人工",
        "售后处理", "客服处理", "帮我派单", "派单处理",
    ]
    GREETING_PATTERNS = [
        r"^你好[啊呀]?[!！。？?]*$", r"^您好[啊呀]?[!！。？?]*$",
        r"^在吗[？?。!！]*$", r"^你是谁[？?。!！]*$",
        r"^测试[一下]*[。!！？?]*$", r"^hello[!！.]*$",
        r"^hi[!！.]*$", r"^哈喽[!！。]*$", r"^嗨[!！。]*$",
    ]
    FUZZY_HANDLE_KEYWORDS = [
        "帮我处理", "帮忙处理", "麻烦处理", "处理一下", "帮我看看",
        "帮忙看看", "麻烦看下", "看一下这个", "这个怎么办",
    ]
    QUESTION_HINTS = [
        "怎么", "如何", "为什么", "哪里", "哪个", "是否", "能不能",
        "可以", "失败", "报错", "看不到", "打不开", "不能", "无法",
    ]

    @classmethod
    def _base_result(
        cls,
        intent: str,
        question: str,
        *,
        category: str = "其他",
        priority: str = "medium",
        source: str = "rule",
        matched: str = "",
    ) -> dict:
        return {
            "intent": intent,
            "summary": question[:100],
            "category": category,
            "priority": priority,
            "classifier_source": source,
            "matched_rule": matched,
        }

    @classmethod
    def _normalize(cls, question: str) -> str:
        return re.sub(r"\s+", "", question or "").lower()

    @classmethod
    def _category_for_ticket(cls, text: str) -> str:
        if any(word in text for word in ["投诉", "不满意", "差评"]):
            return "投诉建议"
        if any(word in text for word in ["数据", "金额", "账", "对账", "统计", "报表"]):
            return "数据问题"
        if any(word in text for word in ["报修", "故障", "打不开", "不能用", "异常", "失败", "报错"]):
            return "系统故障"
        if any(word in text for word in ["怎么", "如何", "咨询", "规则", "流程"]):
            return "业务咨询"
        return "其他"

    @classmethod
    def _priority_for_ticket(cls, text: str) -> str:
        if any(word in text for word in ["紧急", "马上", "立刻", "立即", "严重", "影响营业"]):
            return "urgent"
        if any(word in text for word in ["投诉", "故障", "不能用", "无法使用"]):
            return "high"
        return "medium"

    @classmethod
    def _is_greeting(cls, normalized: str) -> str:
        return next(
            (pattern for pattern in cls.GREETING_PATTERNS if re.match(pattern, normalized)),
            "",
        )

    @classmethod
    def _matched_keyword(cls, normalized: str, keywords: list[str]) -> str:
        return next((word for word in keywords if word in normalized), "")

    @classmethod
    def _needs_llm_fallback(cls, normalized: str) -> bool:
        fuzzy = cls._matched_keyword(normalized, cls.FUZZY_HANDLE_KEYWORDS)
        if not fuzzy:
            return False
        # If the user also provides a concrete business symptom, the RAG path is
        # better: it can retrieve a solution before deciding whether to create a ticket.
        return not any(hint in normalized for hint in cls.QUESTION_HINTS)

    @staticmethod
    async def classify(question: str, user_role: str = "") -> dict:
        """Classify user intent and extract ticket metadata in one call.

        Returns:
            dict with keys: intent, summary, category, priority
            intent is one of: "create_ticket", "answer", "other"
        """
        normalized = IntentClassifier._normalize(question)

        matched_ticket = IntentClassifier._matched_keyword(
            normalized,
            IntentClassifier.TICKET_KEYWORDS,
        )
        if matched_ticket:
            return IntentClassifier._base_result(
                "create_ticket",
                question,
                category=IntentClassifier._category_for_ticket(normalized),
                priority=IntentClassifier._priority_for_ticket(normalized),
                matched=matched_ticket,
            )

        matched_greeting = IntentClassifier._is_greeting(normalized)
        if matched_greeting:
            return IntentClassifier._base_result(
                "other",
                question,
                source="rule",
                matched=matched_greeting,
            )

        if not IntentClassifier._needs_llm_fallback(normalized):
            return IntentClassifier._base_result(
                "answer",
                question,
                source="rule_default",
                matched="business_question_default",
            )

        from app.core.prompt_manager import prompt_manager

        messages = prompt_manager.renderer.render_intent_classifier(
            template_path="classifier/intent_v1.j2",
            user_query=question,
            user_role=user_role,
        )
        try:
            result = await asyncio.wait_for(
                llm_service.chat_json(messages, temperature=0.1),
                timeout=8,
            )
        except Exception:
            return IntentClassifier._base_result(
                "answer",
                question,
                source="llm_fallback_failed",
                matched="timeout_or_error",
            )

        intent = result.get("intent", "answer")
        if intent not in ("create_ticket", "answer", "other"):
            intent = "answer"

        return {
            "intent": intent,
            "summary": result.get("summary", question[:100]),
            "category": result.get("category", "其他"),
            "priority": result.get("priority", "medium"),
            "classifier_source": "llm_fallback",
            "matched_rule": "fuzzy_handle_request",
        }


intent_classifier = IntentClassifier()
