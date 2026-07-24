"""Role-module access control for knowledge retrieval."""
from datetime import datetime
from app.config import settings
from app.models.base import async_session
from app.models.memory import RoleModuleAccess
from sqlalchemy import select


ROLE_LABELS = {
    "school": "学校人员",
    "canteen": "食堂人员",
    "finance": "财务/会计",
    "cashier": "出纳",
    "purchaser": "采购员",
    "storekeeper": "仓管员",
    "distributor": "配送商",
    "inspector": "巡检员",
    "nutritionist": "营养师",
    "education_bureau": "教育局",
    "admin": "管理员",
}


DEFAULT_ROLE_MODULE_MAP = {
    "education_bureau": ["食堂经费监管", "数据驾驶舱", "政策文件", "食安巡检"],
    "school": ["食堂管理", "学校H5", "任务中心", "更多信息", "营养膳食", "预警中心"],
    "canteen": ["食堂管理", "食安监管"],
    "distributor": ["销售管理", "食堂管理"],
    "purchaser": ["食堂管理", "销售管理"],
    "storekeeper": ["食堂管理", "硬件管理"],
    "finance": ["经费管理", "财务管理", "食堂经费监管"],
    "cashier": ["经费管理", "食堂经费监管"],
    "inspector": ["食安巡检", "食安监管"],
    "nutritionist": ["营养膳食", "食堂管理"],
    "admin": [],  # Empty means all modules.
}


class RoleAccessService:
    async def get_role_modules(
        self,
        role: str,
        company_id: str = settings.default_company_id,
    ) -> list[str]:
        company_id = str(company_id or settings.default_company_id)
        role = str(role or "school")
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(RoleModuleAccess).where(
                        RoleModuleAccess.company_id == company_id,
                        RoleModuleAccess.role == role,
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    return list(row.modules or [])
        except Exception:
            pass
        return list(DEFAULT_ROLE_MODULE_MAP.get(role, []))

    async def get_all_permissions(
        self,
        company_id: str = settings.default_company_id,
    ) -> dict[str, list[str]]:
        company_id = str(company_id or settings.default_company_id)
        permissions = {
            role: list(modules)
            for role, modules in DEFAULT_ROLE_MODULE_MAP.items()
        }
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(RoleModuleAccess).where(
                        RoleModuleAccess.company_id == company_id,
                    )
                )
                for row in result.scalars().all():
                    permissions[row.role] = list(row.modules or [])
        except Exception:
            pass
        return permissions

    async def set_role_modules(
        self,
        role: str,
        modules: list[str],
        company_id: str = settings.default_company_id,
        updated_by: str = "admin",
    ) -> dict:
        company_id = str(company_id or settings.default_company_id)
        role = str(role or "school")
        clean_modules = []
        for module in modules or []:
            module = str(module).strip()
            if module and module not in clean_modules:
                clean_modules.append(module)

        async with async_session() as session:
            result = await session.execute(
                select(RoleModuleAccess).where(
                    RoleModuleAccess.company_id == company_id,
                    RoleModuleAccess.role == role,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                row = RoleModuleAccess(
                    company_id=company_id,
                    role=role,
                    modules=clean_modules,
                    updated_by=updated_by,
                )
                session.add(row)
            else:
                row.modules = clean_modules
                row.updated_by = updated_by
                row.updated_at = datetime.utcnow()
            await session.commit()

        return {
            "company_id": company_id,
            "role": role,
            "modules": clean_modules,
            "all_access": role == "admin" and not clean_modules,
        }

    async def reset_role_modules(
        self,
        role: str,
        company_id: str = settings.default_company_id,
    ) -> dict:
        default_modules = list(DEFAULT_ROLE_MODULE_MAP.get(role, []))
        return await self.set_role_modules(
            role=role,
            modules=default_modules,
            company_id=company_id,
            updated_by="system_default",
        )


role_access_service = RoleAccessService()
