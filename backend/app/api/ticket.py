"""Ticket API router."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.ticket_engine import TicketEngine
from app.core.memory_mgr import memory_manager
from app.config import settings

router = APIRouter()
ticket_engine = TicketEngine(memory_manager.redis)


class TicketCreateRequest(BaseModel):
    company_id: str = settings.default_company_id
    original_question: str
    user_id: str = "dev_user"
    user_role: str = "school"
    school_id: str = ""
    trace_id: str = ""


class TicketUpdateRequest(BaseModel):
    status: str | None = None
    category: str | None = None
    priority: str | None = None


@router.post("/create")
async def create_ticket(req: TicketCreateRequest):
    return await ticket_engine.create_draft(
        original_question=req.original_question,
        user_id=req.user_id,
        user_role=req.user_role,
        school_id=req.school_id,
        company_id=req.company_id,
        trace_id=req.trace_id,
    )


@router.get("/list")
async def list_tickets(
    user_id: str = Query(None),
    status: str = Query(None),
    company_id: str = Query(settings.default_company_id),
    limit: int = Query(50, le=200),
):
    return await ticket_engine.list_tickets(
        user_id=user_id, status=status, limit=limit, company_id=str(company_id),
    )


@router.get("/{draft_id}")
async def get_ticket(
    draft_id: str,
    company_id: str = Query(settings.default_company_id),
):
    result = await ticket_engine.get_draft(draft_id, company_id=str(company_id))
    if not result:
        raise HTTPException(status_code=404, detail="工单不存在")
    return result


@router.post("/{draft_id}/submit")
async def submit_ticket(
    draft_id: str,
    company_id: str = Query(settings.default_company_id),
):
    result = await ticket_engine.submit(draft_id, company_id=str(company_id))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.patch("/{draft_id}")
async def update_ticket(
    draft_id: str,
    req: TicketUpdateRequest,
    company_id: str = Query(settings.default_company_id),
):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    return await ticket_engine.update(draft_id, updates, company_id=str(company_id))
