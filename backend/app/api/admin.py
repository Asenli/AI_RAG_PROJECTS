"""Admin API router — stats, traces, badcases, feedback management."""
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from app.core.access_control import role_access_service, ROLE_LABELS
from app.core.feedback_svc import feedback_service
from app.services.vector_store import vector_store
from app.config import settings
from app.core.ragas_eval_service import ragas_evaluation_service

router = APIRouter()


class RoleModulesUpdateRequest(BaseModel):
    modules: list[str] = []


class RagasRunRequest(BaseModel):
    limit: int = 0
    include_ragas: bool = True


def _extract_trace_question(logs) -> str:
    for log in sorted(logs, key=lambda item: item.node_order or 0):
        input_data = log.input_data or {}
        output_data = log.output_data or {}
        for data in [input_data, output_data]:
            question = (
                data.get("question")
                or data.get("safe_question")
                or data.get("rewritten_question")
            )
            if question:
                return str(question)
    return ""


def _trace_status(logs) -> str:
    statuses = [log.status for log in logs if log.status]
    if any(status == "error" for status in statuses):
        return "error"
    if any(status == "warning" for status in statuses):
        return "warning"
    if any(status == "running" for status in statuses):
        return "running"
    return statuses[0] if statuses else "ok"


@router.get("/stats")
async def admin_stats(company_id: str = Query(settings.default_company_id)):
    company_id = str(company_id)
    feedback_stats = await feedback_service.get_stats(days=30, company_id=company_id)
    return {
        "company_id": company_id,
        "total_chunks": vector_store.count(company_id=company_id),
        "status": "healthy",
        "qdrant_mode": "local",
        "feedback_stats": feedback_stats,
    }


@router.post("/ragas/run")
async def run_ragas_evaluation(
    req: RagasRunRequest,
    company_id: str = Query(settings.default_company_id),
):
    try:
        return ragas_evaluation_service.start(str(company_id), req.limit, req.include_ragas)
    except FileNotFoundError as error:
        return {"status": "failed", "error": str(error)}


@router.get("/ragas/status")
async def ragas_evaluation_status():
    return ragas_evaluation_service.status()


@router.get("/role-modules")
async def get_role_modules(company_id: str = Query(settings.default_company_id)):
    company_id = str(company_id)
    source_stats = vector_store.list_source_stats(company_id=company_id)
    modules = sorted({
        item.get("module", "")
        for item in source_stats
        if item.get("module")
    })
    permissions = await role_access_service.get_all_permissions(company_id=company_id)
    return {
        "company_id": company_id,
        "modules": modules,
        "roles": [
            {
                "role": role,
                "label": label,
                "modules": permissions.get(role, []),
                "all_access": role == "admin" and not permissions.get(role, []),
            }
            for role, label in ROLE_LABELS.items()
        ],
    }


@router.put("/role-modules/{role}")
async def update_role_modules(
    role: str,
    req: RoleModulesUpdateRequest,
    request: Request,
    company_id: str = Query(settings.default_company_id),
):
    updated_by = getattr(request.state, "user_id", None) or "admin"
    return await role_access_service.set_role_modules(
        role=role,
        modules=req.modules,
        company_id=str(company_id),
        updated_by=updated_by,
    )


@router.post("/role-modules/{role}/reset")
async def reset_role_modules(
    role: str,
    company_id: str = Query(settings.default_company_id),
):
    return await role_access_service.reset_role_modules(
        role=role,
        company_id=str(company_id),
    )


@router.get("/traces")
async def list_traces(
    user_id: str = Query(None),
    company_id: str = Query(settings.default_company_id),
    limit: int = Query(50),
):
    from app.models.trace import TraceLog
    from app.models.base import async_session
    from sqlalchemy import select
    try:
        async with async_session() as session:
            query = select(TraceLog).where(
                TraceLog.company_id == str(company_id)
            ).order_by(TraceLog.created_at.desc()).limit(limit * 20)
            if user_id:
                query = query.where(TraceLog.user_id == user_id)
            result = await session.execute(query)
            logs = result.scalars().all()
            trace_groups = {}
            for log in logs:
                trace_groups.setdefault(log.trace_id, []).append(log)

            summaries = []
            for trace_id, group_logs in trace_groups.items():
                newest = max(
                    group_logs,
                    key=lambda item: item.created_at,
                )
                ordered_nodes = sorted(
                    group_logs,
                    key=lambda item: item.node_order or 0,
                )
                summaries.append({
                    "trace_id": trace_id,
                    "company_id": newest.company_id,
                    "session_id": newest.session_id,
                    "user_id": newest.user_id,
                    "user_role": newest.user_role,
                    "question": _extract_trace_question(group_logs),
                    "node_count": len(group_logs),
                    "nodes": [node.node_name for node in ordered_nodes],
                    "duration_ms": sum(node.duration_ms or 0 for node in group_logs),
                    "status": _trace_status(group_logs),
                    "created_at": newest.created_at.isoformat() if newest.created_at else None,
                })

            summaries.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            return summaries[:limit]
    except Exception:
        return []


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    company_id: str = Query(settings.default_company_id),
):
    from app.models.trace import TraceLog
    from app.models.base import async_session
    from sqlalchemy import select
    try:
        async with async_session() as session:
            result = await session.execute(
                select(TraceLog)
                .where(
                    TraceLog.trace_id == trace_id,
                    TraceLog.company_id == str(company_id),
                )
                .order_by(TraceLog.node_order)
            )
            logs = result.scalars().all()
            return {
                "trace_id": trace_id,
                "company_id": str(company_id),
                "question": _extract_trace_question(logs),
                "duration_ms": sum(l.duration_ms or 0 for l in logs),
                "status": _trace_status(logs),
                "nodes": [
                    {
                        "node_name": l.node_name,
                        "duration_ms": l.duration_ms,
                        "status": l.status,
                        "input": l.input_data,
                        "output": l.output_data,
                        "error": l.error_message,
                    }
                    for l in logs
                ],
            }
    except Exception:
        return {"trace_id": trace_id, "nodes": []}


@router.get("/badcase/list")
async def list_badcases(
    company_id: str = Query(settings.default_company_id),
    limit: int = Query(50),
):
    from app.models.feedback import AnswerFeedback
    from app.models.base import async_session
    from sqlalchemy import select
    try:
        async with async_session() as session:
            result = await session.execute(
                select(AnswerFeedback)
                .where(
                    AnswerFeedback.is_badcase_candidate == True,
                    AnswerFeedback.company_id == str(company_id),
                )
                .order_by(AnswerFeedback.created_at.desc())
                .limit(limit)
            )
            items = result.scalars().all()
            return [
                {
                    "id": str(i.id),
                    "company_id": i.company_id,
                    "answer_id": i.answer_id,
                    "trace_id": i.trace_id,
                    "user_id": i.user_id,
                    "question": i.question[:200] if i.question else "",
                    "reason": i.reason,
                    "reason_category": i.reason_category,
                    "review_status": i.review_status,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i in items
            ]
    except Exception:
        return []


@router.get("/feedback/list")
async def list_feedback_admin(
    feedback: str = Query(None, alias="feedback_type"),
    review_status: str = Query(None),
    reason_category: str = Query(None),
    company_id: str = Query(settings.default_company_id),
    limit: int = Query(50),
):
    return await feedback_service.list_feedback(
        feedback_type=feedback,
        review_status=review_status,
        reason_category=reason_category,
        company_id=str(company_id),
        limit=limit,
    )


@router.post("/feedback/{feedback_id}/review")
async def review_feedback(
    feedback_id: str,
    company_id: str = Query(settings.default_company_id),
):
    return await feedback_service.review_feedback(
        feedback_id=feedback_id, reviewer="admin",
        status="approved", comment="管理员审核通过",
        company_id=str(company_id),
    )


@router.post("/feedback/{feedback_id}/convert-badcase")
async def convert_to_badcase(
    feedback_id: str,
    company_id: str = Query(settings.default_company_id),
):
    """Manually convert feedback to BadCase candidate."""
    from app.models.feedback import AnswerFeedback
    from app.models.base import async_session
    from sqlalchemy import select
    from uuid import UUID
    try:
        async with async_session() as session:
            result = await session.execute(
                select(AnswerFeedback).where(
                    AnswerFeedback.id == UUID(feedback_id),
                    AnswerFeedback.company_id == str(company_id),
                )
            )
            fb = result.scalar_one_or_none()
            if not fb:
                return {"error": "反馈不存在"}
            fb.is_badcase_candidate = True
            await session.commit()
            return {"status": "converted", "feedback_id": feedback_id}
    except Exception as e:
        return {"error": str(e)}
