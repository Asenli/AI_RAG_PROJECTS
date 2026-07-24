"""Feedback API router — like/dislike/stats."""
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from app.core.feedback_svc import feedback_service
from app.config import settings

router = APIRouter()


class LikeRequest(BaseModel):
    company_id: str = settings.default_company_id
    answer_id: str
    trace_id: str = ""
    session_id: str = ""
    user_id: str = "dev_user"
    user_role: str = "school"
    question: str = ""
    llm_answer: str = ""
    retrieved_sources: list = []


class DislikeRequest(BaseModel):
    company_id: str = settings.default_company_id
    answer_id: str
    reason: str = Field(..., min_length=1)
    reason_category: str = "other"
    trace_id: str = ""
    session_id: str = ""
    user_id: str = "dev_user"
    user_role: str = "school"
    question: str = ""
    llm_answer: str = ""
    retrieved_sources: list = []


@router.post("/like")
async def like(req: LikeRequest):
    return await feedback_service.record_like(
        answer_id=req.answer_id, trace_id=req.trace_id,
        session_id=req.session_id, user_id=req.user_id,
        user_role=req.user_role, question=req.question,
        llm_answer=req.llm_answer, retrieved_sources=req.retrieved_sources,
        company_id=req.company_id,
    )


@router.post("/dislike")
async def dislike(req: DislikeRequest):
    return await feedback_service.record_dislike(
        answer_id=req.answer_id, trace_id=req.trace_id,
        session_id=req.session_id, user_id=req.user_id,
        user_role=req.user_role, reason=req.reason,
        reason_category=req.reason_category, question=req.question,
        llm_answer=req.llm_answer, retrieved_sources=req.retrieved_sources,
        company_id=req.company_id,
    )


@router.get("/stats")
async def stats(
    user_id: str = Query(None),
    days: int = Query(30),
    company_id: str = Query(settings.default_company_id),
):
    return await feedback_service.get_stats(
        user_id=user_id,
        days=days,
        company_id=str(company_id),
    )
