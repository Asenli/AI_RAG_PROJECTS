"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings


async def ensure_company_columns(conn):
    """Lightweight dev migration for company_id multi-tenant columns."""
    from sqlalchemy import text

    for table_name in [
        "ticket_drafts",
        "answer_feedback",
        "trace_log",
        "session_medium_memory",
        "user_profiles",
        "user_facts",
        "user_frequent_questions",
    ]:
        await conn.execute(text(
            f"ALTER TABLE {table_name} "
            "ADD COLUMN IF NOT EXISTS company_id VARCHAR(64) NOT NULL DEFAULT '1'"
        ))
        await conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{table_name}_company_id "
            f"ON {table_name} (company_id)"
        ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB tables (must import all models first)
    from app.models.base import engine, Base
    import app.models.memory   # ensure tables registered on Base.metadata
    import app.models.ticket
    import app.models.feedback
    import app.models.trace
    import app.models.user
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_company_columns(conn)
    # Connect memory manager
    from app.core.memory_mgr import memory_manager
    await memory_manager.connect()
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="售后智能助手",
    description="Food Safety Group Meal After-Sales Smart Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trace middleware
from app.middleware.trace import TraceMiddleware
app.add_middleware(TraceMiddleware)

# Auth middleware (dev-mode: relaxed)
from app.middleware.auth import AuthMiddleware
app.add_middleware(AuthMiddleware)

# Register API routers
from app.api import chat, ticket, feedback, knowledge, session, admin

app.include_router(chat.router, prefix="/chat", tags=["智能问答"])
app.include_router(ticket.router, prefix="/ticket", tags=["售后工单"])
app.include_router(feedback.router, prefix="/feedback", tags=["用户反馈"])
app.include_router(knowledge.router, prefix="/knowledge", tags=["知识库管理"])
app.include_router(session.router, prefix="/session", tags=["会话管理"])
app.include_router(admin.router, prefix="/admin", tags=["管理后台"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
