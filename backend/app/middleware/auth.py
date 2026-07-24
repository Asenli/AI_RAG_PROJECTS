"""Auth middleware — dev-mode relaxed, extracts user from headers or JWT."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

PUBLIC_PATHS = ["/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public paths
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        # Dev mode: extract from headers
        from jose import jwt, JWTError
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token:
            try:
                payload = jwt.decode(
                    token, settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                )
                request.state.user_id = payload.get("user_id", "anonymous")
                request.state.user_role = payload.get("role", "school")
                request.state.company_id = str(payload.get("company_id", settings.default_company_id))
            except JWTError:
                pass  # Allow in dev

        # Fallback: header-based auth for dev
        if not hasattr(request.state, "user_id"):
            request.state.user_id = request.headers.get("X-User-Id", "dev_user")
        if not hasattr(request.state, "user_role"):
            request.state.user_role = request.headers.get("X-User-Role", "school")
        if not hasattr(request.state, "company_id"):
            request.state.company_id = request.headers.get(
                "X-Company-Id",
                settings.default_company_id,
            )

        return await call_next(request)
