"""Trace context and node decorator for full-chain observability."""
import uuid
import time
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:16]}"


def set_trace_id(tid: str):
    trace_id_var.set(tid)


def get_trace_id() -> str:
    return trace_id_var.get()


class TraceNode:
    """Async context manager that logs a trace node to DB on exit."""

    def __init__(self, node_name: str, session_id: str = None,
                 user_id: str = None, user_role: str = None):
        self.node_name = node_name
        self.session_id = session_id
        self.user_id = user_id
        self.user_role = user_role
        self.start_time = None
        self.duration_ms = 0
        self.input_data = None
        self.output_data = None
        self.status = "ok"
        self.error = None

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = int((time.perf_counter() - self.start_time) * 1000)
        if exc_type:
            self.status = "error"
            self.error = str(exc_val)
        # Log to DB
        tid = get_trace_id()
        if tid:
            try:
                from app.models.trace import TraceLog
                from app.models.base import async_session
                async with async_session() as session:
                    log = TraceLog(
                        trace_id=tid,
                        session_id=self.session_id,
                        user_id=self.user_id,
                        user_role=self.user_role,
                        node_name=self.node_name,
                        node_order=0,
                        input_data=self.input_data,
                        output_data=self.output_data,
                        duration_ms=self.duration_ms,
                        status=self.status,
                        error_message=self.error,
                    )
                    session.add(log)
                    await session.commit()
            except Exception:
                pass  # Don't let trace logging break the main flow
        return False  # Don't suppress exceptions
