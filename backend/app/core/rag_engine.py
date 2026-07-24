"""RAG Engine — full retrieval-augmented generation pipeline."""
import uuid
import time
from app.services.embedding_svc import embedding_service
from app.services.sparse_embedding_svc import sparse_embedding_service
from app.services.rerank_svc import rerank_service
from app.services.vector_store import vector_store
from app.services.llm_svc import llm_service
from app.services.input_guard import InputGuard
from app.services.output_guard import OutputGuard
from app.services.intent_classifier import intent_classifier
from app.core.context_assembler import context_assembler
from app.core.feedback_svc import feedback_service
from app.core.access_control import role_access_service
from app.config import settings
from langchain_core.documents import Document

ROLE_PREFIX_MAP = {
    "finance": "财务对账",
    "cashier": "财务出纳",
    "canteen": "食堂管理",
    "purchaser": "采购管理",
    "storekeeper": "库存管理",
    "distributor": "配送管理",
    "inspector": "食安巡检",
    "nutritionist": "营养膳食",
    "school": "学校管理",
    "education_bureau": "教育局监管",
    "admin": "系统管理",
}


class RAGEngine:
    async def _log_trace(
        self,
        trace_id: str,
        session_id: str,
        user_id: str,
        user_role: str,
        node_name: str,
        node_order: int,
        input_data: dict | None = None,
        output_data: dict | None = None,
        duration_ms: int = 0,
        status: str = "ok",
        error_message: str | None = None,
        company_id: str | None = None,
    ):
        try:
            from app.models.trace import TraceLog
            from app.models.base import async_session

            async with async_session() as session:
                session.add(TraceLog(
                    trace_id=trace_id,
                    company_id=str(company_id or settings.default_company_id),
                    session_id=session_id,
                    user_id=user_id,
                    user_role=user_role,
                    node_name=node_name,
                    node_order=node_order,
                    input_data=input_data or {},
                    output_data=output_data or {},
                    duration_ms=duration_ms,
                    status=status,
                    error_message=error_message,
                    trace_meta={"company_id": str(company_id or settings.default_company_id)},
                ))
                await session.commit()
        except Exception:
            pass

    @staticmethod
    def _summarize_docs(docs: list[dict], limit: int = 10) -> list[dict]:
        summary = []
        for doc in docs[:limit]:
            entity = doc.get("entity", {})
            metadata = doc.get("metadata", entity)
            text = doc.get("text") or entity.get("text", "")
            summary.append({
                "source": metadata.get("source", ""),
                "company_id": metadata.get("company_id", ""),
                "header_path": metadata.get("header_path", ""),
                "module": metadata.get("module", ""),
                "sub_module": metadata.get("sub_module", ""),
                "score": doc.get("distance", doc.get("score", 0)),
                "rerank_score": doc.get("rerank_score"),
                "final_score": doc.get("final_score"),
                "text_length": len(text),
                "text_preview": text[:120],
            })
        return summary

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.perf_counter() - started_at) * 1000)

    @staticmethod
    def _summarize_messages(messages: list[dict]) -> list[dict]:
        summary = []
        for index, message in enumerate(messages):
            content = str(message.get("content", ""))
            summary.append({
                "index": index,
                "role": message.get("role", ""),
                "length": len(content),
                "preview": content[:300],
            })
        return summary

    @staticmethod
    def _usage_dict(response) -> dict:
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    async def _chat_with_trace(
        self,
        trace_id: str,
        session_id: str,
        user_id: str,
        user_role: str,
        node_order: int,
        purpose: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
        company_id: str | None = None,
    ) -> str:
        node_t = time.perf_counter()
        input_data = {
            "purpose": purpose,
            "provider": getattr(llm_service, "provider", "unknown"),
            "base_url": settings.llm_base_url,
            "model": llm_service.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "message_count": len(messages),
            "messages": self._summarize_messages(messages),
        }
        try:
            response = await llm_service.create_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            content = response.choices[0].message.content or ""
            await self._log_trace(
                trace_id, session_id, user_id, user_role, "llm_call", node_order,
                input_data=input_data,
                output_data={
                    "purpose": purpose,
                    "response_length": len(content),
                    "response_preview": content[:500],
                    "finish_reason": getattr(response.choices[0], "finish_reason", None),
                    "usage": self._usage_dict(response),
                },
                duration_ms=self._elapsed_ms(node_t),
                company_id=company_id,
            )
            return content
        except Exception as exc:
            await self._log_trace(
                trace_id, session_id, user_id, user_role, "llm_call", node_order,
                input_data=input_data,
                output_data={
                    "purpose": purpose,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc)[:1000],
                },
                duration_ms=self._elapsed_ms(node_t),
                status="error",
                error_message=str(exc)[:1000],
                company_id=company_id,
            )
            raise

    async def _chat_json_with_trace(
        self,
        trace_id: str,
        session_id: str,
        user_id: str,
        user_role: str,
        node_order: int,
        purpose: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        company_id: str | None = None,
    ) -> dict:
        import json

        content = await self._chat_with_trace(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            user_role=user_role,
            node_order=node_order,
            purpose=purpose,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            company_id=company_id,
        )
        return json.loads(content)

    async def query(
        self, question: str, user_role: str, user_id: str,
        session_id: str, school_id: str = None,
        company_id: str = settings.default_company_id,
        trace_id: str | None = None,
    ) -> dict:
        company_id = str(company_id or settings.default_company_id)
        t0 = time.perf_counter()
        trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        answer_id = f"ans_{uuid.uuid4().hex[:8]}"

        # 0. Input guard
        node_t = time.perf_counter()
        safe_q, passed, reason = InputGuard.sanitize(question)
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "input_guard", 1,
            input_data={"question": question},
            output_data={"safe_question": safe_q, "passed": passed, "reason": reason},
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )
        if not passed:
            return {
                "trace_id": trace_id, "answer_id": answer_id,
                "answer": f"⚠️ {reason}", "blocked": True,
                "sources": [], "need_ticket": False,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

        # 0.5 Intent classification — short-circuit ticket requests before costly embedding/retrieval
        node_t = time.perf_counter()
        intent_result = await intent_classifier.classify(safe_q, user_role)
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "intent_classifier", 2,
            input_data={"question": safe_q, "user_role": user_role},
            output_data=intent_result,
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )
        if intent_result["intent"] == "create_ticket":
            elapsed = time.perf_counter() - t0
            return {
                "trace_id": trace_id, "answer_id": answer_id,
                "session_id": session_id,
                "answer": (
                    "已收到您的工单请求。"
                    "正在为您生成工单草稿，确认后由人工客服处理。"
                ),
                "sources": [],
                "need_ticket": True,
                "ticket_draft": {
                    "draft_id": None,  # filled by API layer
                    "status": "draft",
                    "suggested_category": intent_result["category"],
                    "summary": intent_result["summary"],
                    "priority": intent_result["priority"],
                },
                "type": "ticket_draft_created",
                "duration_ms": int(elapsed * 1000),
            }
        if intent_result["intent"] == "other":
            return {
                "trace_id": trace_id,
                "answer_id": answer_id,
                "session_id": session_id,
                "answer": (
                    "您好，我是食安团餐售后智能助手。"
                    "请描述您遇到的业务问题或需要查询的操作流程。"
                ),
                "sources": [],
                "need_ticket": False,
                "ticket_draft": None,
                "type": "smalltalk",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

        # 1. Query rewrite — role prefix injection
        role_prefix = ROLE_PREFIX_MAP.get(user_role, "")
        rewritten_q = f"{role_prefix} | {safe_q}" if role_prefix else safe_q

        # 2. Hybrid search — dense semantic vector + BM25 sparse vector
        node_t = time.perf_counter()
        query_vector = await embedding_service.embed_query(rewritten_q)
        sparse_query_vector = sparse_embedding_service.embed_query(rewritten_q)
        filter_expr = await self._build_filter(user_role, company_id)
        results = vector_store.search(
            query_vector,
            sparse_vector=sparse_query_vector,
            top_k=20,
            filter_expr=filter_expr,
            company_id=company_id,
        )
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "hybrid_retrieval", 3,
            input_data={
                "company_id": company_id,
                "rewritten_question": rewritten_q,
                "filter_expr": filter_expr,
                "top_k": 20,
            },
            output_data={
                "result_count": len(results),
                "results": self._summarize_docs(results),
            },
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )

        if not results:
            node_t = time.perf_counter()
            await self._log_trace(
                trace_id, session_id, user_id, user_role, "no_retrieval_results", 5,
                input_data={"rewritten_question": rewritten_q},
                output_data={"need_ticket": True},
                duration_ms=self._elapsed_ms(node_t),
                status="warning",
                company_id=company_id,
            )
            return {
                "trace_id": trace_id, "answer_id": answer_id,
                "session_id": session_id,
                "answer": (
                    "抱歉，知识库中没有找到相关信息。建议您创建工单，"
                    "由人工客服为您处理。"
                ),
                "sources": [], "need_ticket": True,
                "ticket_draft": None,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

        # 3. Rerank
        node_t = time.perf_counter()
        documents = []
        for r in results:
            entity = r.get("entity", {})
            documents.append({
                "text": entity.get("text", ""),
                "metadata": {
                    "source": entity.get("source", ""),
                    "company_id": entity.get("company_id", ""),
                    "header_path": entity.get("header_path", ""),
                    "module": entity.get("module", ""),
                    "sub_module": entity.get("sub_module", ""),
                    "knowledge_type": entity.get("knowledge_type", ""),
                    "role": entity.get("role", ""),
                    "priority": entity.get("priority", 1.0),
                },
                "score": r.get("distance", 0),
            })

        doc_texts = [d["text"] for d in documents]
        try:
            rr = await rerank_service.rerank(rewritten_q, doc_texts, top_n=5)
        except Exception:
            rr = [
                {"index": i, "relevance_score": documents[i]["score"]}
                for i in range(min(5, len(documents)))
            ]
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "rerank", 5,
            input_data={
                "rewritten_question": rewritten_q,
                "candidate_count": len(documents),
                "candidate_sources": self._summarize_docs([
                    {"metadata": d["metadata"], "text": d["text"], "score": d["score"]}
                    for d in documents
                ]),
            },
            output_data={"rerank_results": rr},
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )

        # Reorder by rerank
        reranked_docs = []
        for item in rr[:5]:
            idx = item.get("index", 0)
            if idx < len(documents):
                doc = documents[idx]
                doc["rerank_score"] = item.get("relevance_score", 0)
                reranked_docs.append(doc)

        # 4. Priority coefficient
        for doc in reranked_docs:
            priority = doc["metadata"].get("priority", 1.0)
            coeff = feedback_service.priority_coefficient(float(priority))
            doc["final_score"] = doc.get("rerank_score", 0) * coeff

        reranked_docs.sort(key=lambda d: d.get("final_score", 0), reverse=True)

        # 5. Confidence gate
        node_t = time.perf_counter()
        top_score = reranked_docs[0]["final_score"] if reranked_docs else 0
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "confidence_gate", 6,
            input_data={"score_threshold": 0.65},
            output_data={
                "top_score": top_score,
                "selected_docs": self._summarize_docs(reranked_docs),
                "route": "generate_answer" if top_score >= 0.65 else "low_confidence",
            },
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )

        if top_score >= 0.65:
            return await self._generate_answer(
                trace_id, answer_id, session_id, rewritten_q, safe_q,
                user_role, user_id, school_id, reranked_docs, t0,
                company_id,
            )
        else:
            return await self._low_confidence_handle(
                trace_id, answer_id, session_id, rewritten_q, safe_q,
                user_role, user_id, school_id, reranked_docs, t0,
                company_id,
            )

    async def _build_filter(self, user_role: str, company_id: str) -> str:
        modules = await role_access_service.get_role_modules(
            user_role,
            company_id=company_id,
        )
        if user_role == "admin" and not modules:
            return ""
        if not modules:
            return "role like \"%all%\""
        module_conds = " or ".join([f"module == \"{m}\"" for m in modules])
        return f"({module_conds}) or (role like \"%all%\")"

    async def _generate_answer(
        self, trace_id, answer_id, session_id, rewritten_q, safe_q,
        user_role, user_id, school_id, docs, started_at, company_id,
    ) -> dict:
        node_t = time.perf_counter()
        lc_docs = [
            Document(page_content=d["text"], metadata=d["metadata"])
            for d in docs
        ]

        system_prompt, doc_messages = await context_assembler.assemble(
            session_id,
            user_id,
            user_role,
            school_id or "",
            safe_q,
            lc_docs,
            company_id=company_id,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户问题：{safe_q}"},
        ]

        try:
            answer = await self._chat_with_trace(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                user_role=user_role,
                node_order=65,
                purpose="generate_answer",
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                company_id=company_id,
            )
        except Exception as e:
            answer = f"抱歉，AI服务暂时不可用。错误：{str(e)[:200]}"

        answer = OutputGuard.sanitize(answer)
        answer_duration = self._elapsed_ms(node_t)

        sources = [
            {
                "source": d["metadata"].get("source", ""),
                "company_id": d["metadata"].get("company_id", ""),
                "title": d["metadata"].get(
                    "header_path", d["metadata"].get("source", "")
                ),
                "score": round(d.get("final_score", 0), 4),
            }
            for d in docs
        ]

        await self._log_trace(
            trace_id, session_id, user_id, user_role, "generate_answer", 7,
            input_data={
                "rewritten_question": rewritten_q,
                "question": safe_q,
                "source_count": len(docs),
            },
            output_data={
                "answer_length": len(answer),
                "source_count": len(sources),
            },
            duration_ms=answer_duration,
            company_id=company_id,
        )

        return {
            "trace_id": trace_id, "answer_id": answer_id,
            "session_id": session_id, "answer": answer,
            "sources": sources, "need_ticket": False,
            "duration_ms": self._elapsed_ms(started_at),
        }

    async def _low_confidence_handle(
        self, trace_id, answer_id, session_id, rewritten_q, safe_q,
        user_role, user_id, school_id, docs, started_at, company_id,
    ) -> dict:
        node_t = time.perf_counter()
        doc_text = "\n---\n".join([d["text"][:200] for d in docs])

        judge_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个食安团餐系统的智能助手。用户提出了一个问题，知识库中可能没有直接答案。\n"
                    "请判断问题类型，再决定处理方式。\n"
                    "返回JSON格式：\n"
                    '{"question_type":"operation|policy|finance|food_safety|business_data|after_sales|other",'
                    '"can_answer":true/false,"action":"answer|create_ticket|refuse",'
                    '"answer":"...","need_ticket":true/false,'
                    '"ticket_summary":"工单摘要","refuse_reason":"拒答原因"}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{safe_q}\n\n"
                    f"检索到的相关信息：{doc_text}\n"
                    f"角色：{user_role}"
                ),
            },
        ]

        try:
            judgment = await self._chat_json_with_trace(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                user_role=user_role,
                node_order=65,
                purpose="low_confidence_judge",
                messages=judge_messages,
                temperature=0.1,
                max_tokens=1024,
                company_id=company_id,
            )
        except Exception:
            judgment = {
                "action": "create_ticket", "need_ticket": True,
                "ticket_summary": safe_q[:100],
            }

        action = judgment.get("action", "refuse")

        if action == "answer" and judgment.get("can_answer"):
            lc_docs = [
                Document(page_content=d["text"], metadata=d["metadata"])
                for d in docs
            ]
            system_prompt, _ = await context_assembler.assemble(
                session_id,
                user_id,
                user_role,
                school_id or "",
                safe_q,
                lc_docs,
                company_id=company_id,
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"用户问题：{safe_q}"},
            ]
            try:
                answer = await self._chat_with_trace(
                    trace_id=trace_id,
                    session_id=session_id,
                    user_id=user_id,
                    user_role=user_role,
                    node_order=66,
                    purpose="low_confidence_answer",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                    company_id=company_id,
                )
            except Exception:
                answer = judgment.get(
                    "answer",
                    "抱歉，暂时无法生成回答，请稍后重试。",
                )
            answer = OutputGuard.sanitize(answer)
            await self._log_trace(
                trace_id, session_id, user_id, user_role, "low_confidence", 7,
                input_data={
                    "rewritten_question": rewritten_q,
                    "question": safe_q,
                    "source_count": len(docs),
                },
                output_data={
                    "action": action,
                    "answer_length": len(answer),
                },
                duration_ms=self._elapsed_ms(node_t),
                company_id=company_id,
            )
            return {
                "trace_id": trace_id, "answer_id": answer_id,
                "session_id": session_id, "answer": answer,
                "sources": [], "need_ticket": False,
                "duration_ms": self._elapsed_ms(started_at),
            }

        if action == "refuse":
            await self._log_trace(
                trace_id, session_id, user_id, user_role, "low_confidence", 7,
                input_data={
                    "rewritten_question": rewritten_q,
                    "question": safe_q,
                    "source_count": len(docs),
                },
                output_data={
                    "action": action,
                    "refuse_reason": judgment.get("refuse_reason", ""),
                },
                duration_ms=self._elapsed_ms(node_t),
                company_id=company_id,
            )
            return {
                "trace_id": trace_id, "answer_id": answer_id,
                "session_id": session_id,
                "answer": judgment.get(
                    "refuse_reason",
                    "抱歉，我暂时无法回答这个问题。建议您联系人工售后处理。",
                ),
                "sources": [], "need_ticket": False,
                "duration_ms": self._elapsed_ms(started_at),
            }

        # action == "create_ticket"
        await self._log_trace(
            trace_id, session_id, user_id, user_role, "low_confidence", 7,
            input_data={
                "rewritten_question": rewritten_q,
                "question": safe_q,
                "source_count": len(docs),
            },
            output_data={
                "action": action,
                "need_ticket": True,
                "ticket_summary": judgment.get("ticket_summary", safe_q[:100]),
            },
            duration_ms=self._elapsed_ms(node_t),
            company_id=company_id,
        )
        return {
            "trace_id": trace_id, "answer_id": answer_id,
            "session_id": session_id,
            "answer": (
                "抱歉，我暂时无法回答这个问题。"
                "已为您生成工单草稿，确认后由人工客服处理。"
            ),
            "sources": [],
            "need_ticket": True,
            "ticket_draft": {
                "draft_id": None,  # filled by API layer
                "status": "draft",
                "suggested_category": judgment.get("question_type", "其他"),
                "summary": judgment.get("ticket_summary", safe_q[:100]),
            },
            "type": "ticket_draft_created",
            "duration_ms": self._elapsed_ms(started_at),
        }

    async def search_test(
        self,
        query: str,
        user_role: str,
        top_k: int = 10,
        company_id: str = settings.default_company_id,
    ) -> dict:
        """Search knowledge base without LLM generation, with stage diagnostics."""
        company_id = str(company_id or settings.default_company_id)
        role_prefix = ROLE_PREFIX_MAP.get(user_role, "")
        rewritten_q = f"{role_prefix} | {query}" if role_prefix else query
        query_vector = await embedding_service.embed_query(rewritten_q)
        sparse_query_vector = sparse_embedding_service.embed_query(rewritten_q)
        filter_expr = await self._build_filter(user_role, company_id)
        stage_results = vector_store.debug_search(
            query_vector,
            sparse_vector=sparse_query_vector,
            top_k=top_k,
            filter_expr=filter_expr,
            company_id=company_id,
        )

        def format_results(results: list[dict], score_key: str = "score") -> list[dict]:
            return [
                {
                    "id": r.get("id"),
                    "text": r.get("entity", {}).get("text", "")[:300],
                    "source": r.get("entity", {}).get("source", ""),
                    "company_id": r.get("entity", {}).get("company_id", ""),
                    "module": r.get("entity", {}).get("module", ""),
                    "sub_module": r.get("entity", {}).get("sub_module", ""),
                    "header_path": r.get("entity", {}).get("header_path", ""),
                    score_key: r.get("distance", 0),
                    "score": r.get("distance", 0),
                }
                for r in results
            ]

        hybrid_results = stage_results["hybrid"]
        hybrid_texts = [r.get("entity", {}).get("text", "") for r in hybrid_results]
        try:
            rerank_items = await rerank_service.rerank(
                rewritten_q,
                hybrid_texts,
                top_n=min(top_k, settings.rerank_top_n),
            )
        except Exception:
            rerank_items = [
                {"index": i, "relevance_score": hybrid_results[i].get("distance", 0)}
                for i in range(min(top_k, len(hybrid_results)))
            ]

        reranked = []
        for item in rerank_items:
            idx = item.get("index", 0)
            if idx < len(hybrid_results):
                row = format_results([hybrid_results[idx]], score_key="retrieval_score")[0]
                row["rerank_score"] = item.get("relevance_score", 0)
                row["score"] = row["rerank_score"]
                row["hybrid_rank"] = idx + 1
                reranked.append(row)

        return {
            "query": query,
            "rewritten_query": rewritten_q,
            "role": user_role,
            "company_id": company_id,
            "filter_expr": filter_expr,
            "top_k": top_k,
            "stages": {
                "dense": format_results(stage_results["dense"], score_key="dense_score"),
                "bm25": format_results(stage_results["bm25"], score_key="bm25_score"),
                "hybrid": format_results(stage_results["hybrid"], score_key="hybrid_score"),
                "rerank": reranked,
            },
            "results": reranked,
        }


rag_engine = RAGEngine()
