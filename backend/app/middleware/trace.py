"""Trace middleware — injects trace_id into every request."""
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.trace import trace_id_var


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id", f"trace_{uuid.uuid4().hex[:16]}")
        trace_id_var.set(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
