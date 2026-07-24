"""Role-based access control dependency injection."""
from fastapi import Depends, HTTPException, Request


class RoleChecker:
    """FastAPI dependency that checks user role against allowed list."""

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, request: Request):
        user_role = getattr(request.state, "user_role", "school")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"角色 {user_role} 无权访问此功能",
            )
        return request.state


# Convenience presets
admin_only = RoleChecker(["admin"])
