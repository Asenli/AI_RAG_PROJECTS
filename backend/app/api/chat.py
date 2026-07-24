"""Chat / Q&A API router."""
import uuid
import time
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from app.core.rag_engine import rag_engine
from app.core.ticket_engine import TicketEngine
from app.core.memory_mgr import memory_manager
from app.core.trace import get_trace_id
from app.config import settings

router = APIRouter()
ticket_engine = TicketEngine(memory_manager.redis)
FRIENDLY_ERROR_ANSWER = (
    "抱歉，系统刚才处理请求时遇到异常。请稍后再试，"
    "如果问题持续出现，请联系管理员并提供本次 Trace ID。"
)


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class ChatRequest(BaseModel):
    company_id: str = Field(default=settings.default_company_id)
    session_id: str = ""
    question: str = Field(..., min_length=1, max_length=500)
    user_id: str = Field(default="dev_user")
    user_role: str = Field(
        default="school",
        description="education_bureau|school|canteen|distributor|purchaser|storekeeper|finance|cashier|inspector|nutritionist|admin",
    )
    school_id: str = ""


class ChatResponse(BaseModel):
    company_id: str = settings.default_company_id
    trace_id: str
    answer_id: str
    session_id: str = ""
    answer: str
    sources: list = []
    need_ticket: bool = False
    ticket_draft: dict | None = None
    duration_ms: int = 0
    blocked: bool = False
    type: str = ""


@router.post("/ask")
async def ask(req: ChatRequest, request: Request):
    started_at = time.perf_counter()
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    trace_id = get_trace_id() or f"trace_{uuid.uuid4().hex[:16]}"
    answer_id = f"ans_{uuid.uuid4().hex[:8]}"

    # Override role from header if present
    user_role = getattr(request.state, "user_role", None) or req.user_role
    user_id = getattr(request.state, "user_id", None) or req.user_id
    company_id = str(getattr(request.state, "company_id", None) or req.company_id or settings.default_company_id)

    try:
        await memory_manager.register_session(
            session_id,
            user_id=user_id,
            user_role=user_role,
            school_id=req.school_id,
            company_id=company_id,
            title=req.question,
        )
        result = await rag_engine.query(
            question=req.question,
            user_role=user_role,
            user_id=user_id,
            session_id=session_id,
            school_id=req.school_id,
            company_id=company_id,
            trace_id=trace_id,
        )

        # Auto-create ticket draft if needed
        if result.get("need_ticket") and not result.get("blocked"):
            existing_draft = result.get("ticket_draft") or {}
            try:
                draft = await ticket_engine.create_draft(
                    original_question=req.question,
                    user_id=user_id,
                    user_role=user_role,
                    school_id=req.school_id,
                    company_id=company_id,
                    trace_id=result["trace_id"],
                    llm_judgment={
                        "ticket_summary": existing_draft.get("summary", req.question[:100]),
                        "question_type": existing_draft.get("suggested_category", "其他"),
                    },
                )
                if not result.get("ticket_draft"):
                    result["ticket_draft"] = {}
                result["ticket_draft"]["draft_id"] = draft.get("draft_id")
                # Preserve intent-classifier fields in response
                if existing_draft.get("summary"):
                    result["ticket_draft"]["summary"] = existing_draft["summary"]
                if existing_draft.get("suggested_category"):
                    result["ticket_draft"]["suggested_category"] = existing_draft["suggested_category"]
                if existing_draft.get("priority"):
                    result["ticket_draft"]["priority"] = existing_draft["priority"]
            except Exception as draft_error:
                # Draft creation failed but answer is still valid
                result["need_ticket"] = False
                result["ticket_draft"] = {"draft_id": None, "status": "creation_failed"}
                await rag_engine._log_trace(
                    result["trace_id"], session_id, user_id, user_role, "ticket_draft_error", 98,
                    input_data={"question": req.question},
                    output_data={
                        "friendly_result": "工单草稿创建失败，已返回普通回答",
                        "error_type": draft_error.__class__.__name__,
                        "error_message": str(draft_error)[:500],
                    },
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    status="warning",
                    company_id=company_id,
                )

        # Save final Q&A to short-term memory after all response fields are settled.
        await memory_manager.append_short_term(
            session_id,
            {
                "round": 0, "role": "user", "content": req.question,
                "company_id": company_id, "timestamp": _now_iso(),
            },
            company_id=company_id,
        )
        await memory_manager.persist_message(
            session_id,
            role="user",
            content=req.question,
            user_id=user_id,
            user_role=user_role,
            company_id=company_id,
            metadata={"company_id": company_id},
            school_id=req.school_id,
            title=req.question,
        )
        assistant_metadata = {
            "trace_id": result["trace_id"],
            "answer_id": result.get("answer_id"),
            "sources": result.get("sources", []),
            "need_ticket": result.get("need_ticket", False),
            "ticket_draft": result.get("ticket_draft"),
            "duration_ms": result.get("duration_ms"),
            "company_id": company_id,
        }
        history = await memory_manager.append_short_term(
            session_id,
            {
                "round": 0, "role": "assistant", "content": result["answer"],
                "metadata": assistant_metadata,
                "timestamp": _now_iso(),
            },
            company_id=company_id,
        )
        await memory_manager.persist_message(
            session_id,
            role="assistant",
            content=result["answer"],
            user_id=user_id,
            user_role=user_role,
            company_id=company_id,
            metadata=assistant_metadata,
            trace_id=result["trace_id"],
            answer_id=result.get("answer_id"),
            school_id=req.school_id,
            title=req.question,
        )
        await memory_manager.touch_session(
            session_id,
            user_id=user_id,
            user_role=user_role,
            school_id=req.school_id,
            company_id=company_id,
            title=req.question,
            message_count=len(history),
        )

        await rag_engine._log_trace(
            result["trace_id"], session_id, user_id, user_role, "api_response", 99,
            input_data={"question": req.question},
            output_data={
                "status": "success",
                "answer_id": result.get("answer_id"),
                "answer_length": len(result.get("answer", "")),
                "source_count": len(result.get("sources", [])),
                "need_ticket": result.get("need_ticket", False),
                "blocked": result.get("blocked", False),
            },
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            company_id=company_id,
        )

        return ChatResponse(**{
            **result,
            "company_id": company_id,
            "session_id": session_id,
        })
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            await memory_manager.register_session(
                session_id,
                user_id=user_id,
                user_role=user_role,
                school_id=req.school_id,
                company_id=company_id,
                title=req.question,
            )
            await memory_manager.append_short_term(
                session_id,
                {
                    "round": 0, "role": "user", "content": req.question,
                    "company_id": company_id, "timestamp": _now_iso(),
                },
                company_id=company_id,
            )
            await memory_manager.persist_message(
                session_id,
                role="user",
                content=req.question,
                user_id=user_id,
                user_role=user_role,
                company_id=company_id,
                metadata={"company_id": company_id},
                school_id=req.school_id,
                title=req.question,
            )
            error_metadata = {
                "trace_id": trace_id,
                "answer_id": answer_id,
                "duration_ms": duration_ms,
                "company_id": company_id,
                "type": "system_error",
            }
            history = await memory_manager.append_short_term(
                session_id,
                {
                    "round": 0, "role": "assistant", "content": FRIENDLY_ERROR_ANSWER,
                    "metadata": error_metadata,
                    "timestamp": _now_iso(),
                },
                company_id=company_id,
            )
            await memory_manager.persist_message(
                session_id,
                role="assistant",
                content=FRIENDLY_ERROR_ANSWER,
                user_id=user_id,
                user_role=user_role,
                company_id=company_id,
                metadata=error_metadata,
                trace_id=trace_id,
                answer_id=answer_id,
                school_id=req.school_id,
                title=req.question,
            )
            await memory_manager.touch_session(
                session_id,
                user_id=user_id,
                user_role=user_role,
                school_id=req.school_id,
                company_id=company_id,
                title=req.question,
                message_count=len(history),
            )
        except Exception:
            pass
        await rag_engine._log_trace(
            trace_id, session_id, user_id, user_role, "api_error", 99,
            input_data={
                "question": req.question,
                "user_id": user_id,
                "user_role": user_role,
                "company_id": company_id,
            },
            output_data={
                "status": "error",
                "friendly_answer": FRIENDLY_ERROR_ANSWER,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:1000],
            },
            duration_ms=duration_ms,
            status="error",
            error_message=str(exc)[:1000],
            company_id=company_id,
        )
        return ChatResponse(
            company_id=company_id,
            trace_id=trace_id,
            answer_id=answer_id,
            session_id=session_id,
            answer=FRIENDLY_ERROR_ANSWER,
            sources=[],
            need_ticket=False,
            ticket_draft=None,
            duration_ms=duration_ms,
            blocked=False,
            type="system_error",
        )


@router.get("/answer/{answer_id}")
async def get_answer(answer_id: str):
    """Retrieve an answer by ID (for sharing/debugging)."""
    return {"answer_id": answer_id, "message": "Answer lookup not yet implemented"}
