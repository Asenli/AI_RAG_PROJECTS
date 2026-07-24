"""Ticket engine — draft creation, dedup, submission, listing."""
import uuid
import hashlib
import json
from datetime import datetime
from app.models.ticket import TicketDraft
from app.models.base import async_session
from app.config import settings
from sqlalchemy import select


class TicketEngine:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def create_draft(
        self,
        original_question: str,
        user_id: str,
        user_role: str,
        school_id: str = None,
        company_id: str = settings.default_company_id,
        trace_id: str = None,
        llm_judgment: dict = None,
        retrieval_scores: list = None,
        top_docs_summary: str = None,
    ) -> dict:
        company_id = str(company_id or settings.default_company_id)
        # Dedup check (30 min window)
        if self.redis:
            dedup_slug = hashlib.md5(original_question.encode()).hexdigest()[:10]
            dedup_key = f"ticket:dedup:{company_id}:{user_id}:{dedup_slug}"
            try:
                existing_id = self.redis.get(dedup_key)
                if existing_id:
                    return {
                        "draft_id": existing_id,
                        "status": "duplicate",
                        "message": "30分钟内已有相似工单",
                    }
            except Exception:
                pass  # Redis optional

        draft_id = f"draft_{uuid.uuid4().hex[:12]}"

        llm_data = None
        if isinstance(llm_judgment, dict):
            llm_data = llm_judgment
        elif isinstance(llm_judgment, str) and llm_judgment:
            try:
                llm_data = json.loads(llm_judgment)
            except json.JSONDecodeError:
                pass

        draft = TicketDraft(
            draft_id=draft_id,
            status="draft",
            company_id=company_id,
            original_question=original_question,
            user_id=user_id,
            user_role=user_role,
            school_id=school_id,
            trace_id=trace_id,
            llm_judgment=llm_data,
            retrieval_scores=retrieval_scores or [],
            top_docs_summary=top_docs_summary,
            suggested_category=llm_data.get("ticket_summary", "") if llm_data else "",
            category=llm_data.get("question_type", "其他") if llm_data else "其他",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        async with async_session() as session:
            session.add(draft)
            await session.commit()

        # Set dedup key (30 min TTL)
        if self.redis:
            try:
                dedup_slug = hashlib.md5(original_question.encode()).hexdigest()[:10]
                self.redis.setex(
                    f"ticket:dedup:{company_id}:{user_id}:{dedup_slug}",
                    1800,
                    draft_id,
                )
            except Exception:
                pass

        return {
            "draft_id": draft_id,
            "company_id": company_id,
            "status": "draft",
            "suggested_category": draft.suggested_category or "",
            "summary": draft.original_question[:100],
        }

    async def get_draft(
        self,
        draft_id: str,
        company_id: str = settings.default_company_id,
    ) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(TicketDraft).where(
                    TicketDraft.draft_id == draft_id,
                    TicketDraft.company_id == str(company_id or settings.default_company_id),
                )
            )
            draft = result.scalar_one_or_none()
            if not draft:
                return None
            return {
                "draft_id": draft.draft_id,
                "company_id": draft.company_id,
                "status": draft.status,
                "original_question": draft.original_question,
                "user_id": draft.user_id,
                "user_role": draft.user_role,
                "school_id": draft.school_id,
                "category": draft.category,
                "priority": draft.priority,
                "suggested_category": draft.suggested_category,
                "trace_id": draft.trace_id,
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
                "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
            }

    async def submit(
        self,
        draft_id: str,
        company_id: str = settings.default_company_id,
    ) -> dict:
        async with async_session() as session:
            result = await session.execute(
                select(TicketDraft).where(
                    TicketDraft.draft_id == draft_id,
                    TicketDraft.company_id == str(company_id or settings.default_company_id),
                )
            )
            draft = result.scalar_one_or_none()
            if not draft:
                return {"error": "工单草稿不存在"}
            if draft.status != "draft":
                return {"error": f"工单状态为 {draft.status}，无法提交"}
            ticket_id = f"ticket_{uuid.uuid4().hex[:12]}"
            draft.status = "submitted"
            draft.updated_at = datetime.utcnow()
            await session.commit()
            return {
                "ticket_id": ticket_id,
                "draft_id": draft_id,
                "company_id": draft.company_id,
                "status": "submitted",
                "message": "工单已正式提交",
            }

    async def list_tickets(
        self,
        user_id: str = None,
        status: str = None,
        limit: int = 50,
        company_id: str = settings.default_company_id,
    ) -> list:
        async with async_session() as session:
            query = select(TicketDraft).where(
                TicketDraft.company_id == str(company_id or settings.default_company_id)
            ).order_by(TicketDraft.created_at.desc())
            if user_id:
                query = query.where(TicketDraft.user_id == user_id)
            if status:
                query = query.where(TicketDraft.status == status)
            query = query.limit(limit)
            result = await session.execute(query)
            drafts = result.scalars().all()
            return [
                {
                    "draft_id": d.draft_id,
                    "company_id": d.company_id,
                    "status": d.status,
                    "original_question": d.original_question,
                    "category": d.category,
                    "priority": d.priority,
                    "user_role": d.user_role,
                    "user_id": d.user_id,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in drafts
            ]

    async def update(
        self,
        draft_id: str,
        updates: dict,
        company_id: str = settings.default_company_id,
    ) -> dict:
        async with async_session() as session:
            result = await session.execute(
                select(TicketDraft).where(
                    TicketDraft.draft_id == draft_id,
                    TicketDraft.company_id == str(company_id or settings.default_company_id),
                )
            )
            draft = result.scalar_one_or_none()
            if not draft:
                return {"error": "工单草稿不存在"}
            for key, value in updates.items():
                if hasattr(draft, key):
                    setattr(draft, key, value)
            draft.updated_at = datetime.utcnow()
            await session.commit()
            return {"draft_id": draft_id, "status": draft.status, "message": "更新成功"}
