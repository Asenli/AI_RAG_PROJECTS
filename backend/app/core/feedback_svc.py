"""Feedback service — record likes/dislikes, review, stats, priority coefficient."""
from datetime import datetime, timedelta
from app.models.feedback import AnswerFeedback
from app.models.base import async_session
from app.config import settings
from sqlalchemy import select, func


class FeedbackService:
    @staticmethod
    def priority_coefficient(priority: float) -> float:
        """Map priority 1.0~5.0 → coefficient 1.00~1.30."""
        return 1.0 + (priority - 1.0) * 0.075

    async def record_like(
        self, answer_id: str, trace_id: str, session_id: str,
        user_id: str, user_role: str, question: str,
        llm_answer: str, retrieved_sources: list,
        company_id: str = settings.default_company_id,
    ) -> dict:
        try:
            company_id = str(company_id or settings.default_company_id)
            async with async_session() as session:
                fb = AnswerFeedback(
                    company_id=company_id,
                    answer_id=answer_id, trace_id=trace_id, session_id=session_id,
                    user_id=user_id, user_role=user_role, feedback="like",
                    question=question, llm_answer=llm_answer,
                    retrieved_sources=retrieved_sources,
                    review_status="pending_review", created_at=datetime.utcnow(),
                )
                session.add(fb)
                await session.commit()
            return {"status": "recorded", "feedback": "like", "pending_review": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def record_dislike(
        self, answer_id: str, trace_id: str, session_id: str,
        user_id: str, user_role: str, reason: str, reason_category: str,
        question: str, llm_answer: str, retrieved_sources: list,
        company_id: str = settings.default_company_id,
    ) -> dict:
        try:
            company_id = str(company_id or settings.default_company_id)
            async with async_session() as session:
                # Rate limit: same user + category, 24h, max 3
                cutoff = datetime.utcnow() - timedelta(hours=24)
                count_result = await session.execute(
                    select(func.count()).where(
                        AnswerFeedback.user_id == user_id,
                        AnswerFeedback.company_id == company_id,
                        AnswerFeedback.feedback == "dislike",
                        AnswerFeedback.reason_category == reason_category,
                        AnswerFeedback.created_at >= cutoff,
                    )
                )
                recent_count = count_result.scalar()
                is_badcase = recent_count < 3 and bool(reason)

                fb = AnswerFeedback(
                    company_id=company_id,
                    answer_id=answer_id, trace_id=trace_id, session_id=session_id,
                    user_id=user_id, user_role=user_role, feedback="dislike",
                    reason=reason, reason_category=reason_category,
                    question=question, llm_answer=llm_answer,
                    retrieved_sources=retrieved_sources,
                    review_status="pending_review",
                    is_badcase_candidate=is_badcase,
                    created_at=datetime.utcnow(),
                )
                session.add(fb)
                await session.commit()
            return {
                "status": "recorded", "feedback": "dislike",
                "is_badcase_candidate": is_badcase, "pending_review": True,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_stats(
        self,
        user_id: str = None,
        days: int = 30,
        company_id: str = settings.default_company_id,
    ) -> dict:
        try:
            company_id = str(company_id or settings.default_company_id)
            async with async_session() as session:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = select(AnswerFeedback).where(
                    AnswerFeedback.company_id == company_id,
                    AnswerFeedback.created_at >= cutoff
                )
                if user_id:
                    query = query.where(AnswerFeedback.user_id == user_id)
                result = await session.execute(query)
                feedbacks = result.scalars().all()

                likes = sum(1 for f in feedbacks if f.feedback == "like")
                dislikes = sum(1 for f in feedbacks if f.feedback == "dislike")
                total = likes + dislikes
                satisfaction = likes / total if total > 0 else 0

                return {
                    "total": total, "likes": likes, "dislikes": dislikes,
                    "satisfaction_rate": round(satisfaction, 4),
                    "days": days,
                    "company_id": company_id,
                }
        except Exception:
            return {"total": 0, "likes": 0, "dislikes": 0, "satisfaction_rate": 0, "days": days}

    async def list_feedback(
        self, feedback_type: str = None, review_status: str = None,
        reason_category: str = None, limit: int = 50,
        company_id: str = settings.default_company_id,
    ) -> list:
        try:
            company_id = str(company_id or settings.default_company_id)
            async with async_session() as session:
                query = select(AnswerFeedback).where(
                    AnswerFeedback.company_id == company_id
                ).order_by(
                    AnswerFeedback.created_at.desc()
                )
                if feedback_type:
                    query = query.where(AnswerFeedback.feedback == feedback_type)
                if review_status:
                    query = query.where(AnswerFeedback.review_status == review_status)
                if reason_category:
                    query = query.where(AnswerFeedback.reason_category == reason_category)
                query = query.limit(limit)
                result = await session.execute(query)
                items = result.scalars().all()
                return [
                    {
                        "id": str(i.id), "answer_id": i.answer_id,
                        "company_id": i.company_id,
                        "user_id": i.user_id, "feedback": i.feedback,
                        "reason": i.reason, "reason_category": i.reason_category,
                        "question": i.question[:100] if i.question else "",
                        "review_status": i.review_status,
                        "is_badcase_candidate": i.is_badcase_candidate,
                        "created_at": i.created_at.isoformat() if i.created_at else None,
                    }
                    for i in items
                ]
        except Exception:
            return []

    async def review_feedback(
        self,
        feedback_id: str,
        reviewer: str,
        status: str,
        comment: str = "",
        company_id: str = settings.default_company_id,
    ) -> dict:
        try:
            from uuid import UUID
            async with async_session() as session:
                result = await session.execute(
                    select(AnswerFeedback).where(
                        AnswerFeedback.id == UUID(feedback_id),
                        AnswerFeedback.company_id == str(company_id or settings.default_company_id),
                    )
                )
                fb = result.scalar_one_or_none()
                if not fb:
                    return {"error": "反馈不存在"}
                fb.review_status = status
                fb.reviewed_by = reviewer
                fb.reviewed_at = datetime.utcnow()
                fb.review_comment = comment
                await session.commit()
            return {"status": "reviewed", "review_status": status}
        except Exception as e:
            return {"error": str(e)}


feedback_service = FeedbackService()
