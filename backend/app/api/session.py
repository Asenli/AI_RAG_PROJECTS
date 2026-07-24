"""Session management API router."""
import uuid
from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.core.memory_mgr import memory_manager
from app.config import settings

router = APIRouter()


class SessionCreateRequest(BaseModel):
    company_id: str = settings.default_company_id
    user_id: str = "dev_user"
    user_role: str = "school"
    school_id: str = ""


@router.post("/create")
async def create_session(req: SessionCreateRequest):
    company_id = str(req.company_id or settings.default_company_id)
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    if memory_manager.redis:
        import json
        try:
            await memory_manager.redis.setex(
                memory_manager._session_key(company_id, session_id, "short_term"),
                1209600,
                json.dumps([], ensure_ascii=False),
            )
        except Exception:
            pass
    await memory_manager.register_session(
        session_id,
        user_id=req.user_id,
        user_role=req.user_role,
        school_id=req.school_id,
        company_id=company_id,
    )
    profile = await memory_manager.get_user_profile(req.user_id, company_id=company_id)
    return {
        "company_id": company_id,
        "session_id": session_id,
        "user_id": req.user_id,
        "user_role": req.user_role,
        "profile": profile,
    }


@router.get("/list")
async def list_sessions(
    company_id: str = Query(settings.default_company_id),
    user_id: str = Query("dev_user"),
    limit: int = Query(30, ge=1, le=100),
):
    sessions = await memory_manager.list_sessions(
        user_id=user_id,
        company_id=str(company_id),
        limit=limit,
    )
    return {
        "company_id": str(company_id),
        "user_id": user_id,
        "sessions": sessions,
        "total": len(sessions),
    }


@router.get("/{session_id}/history")
async def get_history(
    session_id: str,
    company_id: str = Query(settings.default_company_id),
    limit: int = Query(500, ge=1, le=2000),
):
    history = await memory_manager.get_persistent_history(
        session_id,
        company_id=str(company_id),
        limit=limit,
    )
    return {
        "company_id": str(company_id),
        "session_id": session_id,
        "history": history,
        "rounds": len(history) // 2 if history else 0,
    }


@router.get("/{session_id}/summary")
async def get_summary(
    session_id: str,
    company_id: str = Query(settings.default_company_id),
):
    summary = await memory_manager.get_medium_term(
        session_id,
        company_id=str(company_id),
    )
    return {
        "company_id": str(company_id),
        "session_id": session_id,
        "summary": summary.get("summary", ""),
        "version": summary.get("version", 0),
    }


@router.get("/user/{user_id}/profile")
async def get_user_profile(
    user_id: str,
    company_id: str = Query(settings.default_company_id),
):
    company_id = str(company_id)
    profile = await memory_manager.get_user_profile(user_id, company_id=company_id)
    facts = await memory_manager.get_user_facts(user_id, limit=10, company_id=company_id)
    freq_qs = await memory_manager.get_frequent_questions(user_id, limit=5, company_id=company_id)
    return {
        "company_id": company_id,
        "user_id": user_id,
        "profile": profile,
        "facts": facts,
        "frequent_questions": freq_qs,
    }


@router.delete("/{session_id}")
async def close_session(
    session_id: str,
    company_id: str = Query(settings.default_company_id),
):
    await memory_manager.delete_session(session_id, company_id=str(company_id))
    return {"status": "closed", "session_id": session_id}
