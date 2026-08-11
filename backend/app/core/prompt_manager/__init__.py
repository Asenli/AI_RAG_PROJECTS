"""Prompt Manager — 统一入口，组合 loader + builder + renderer + version + safety."""
from __future__ import annotations
from typing import Optional
from app.core.prompt_manager.loader import PromptLoader
from app.core.prompt_manager.builder import ContextBuilder, BuildMode
from app.core.prompt_manager.renderer import PromptRenderer
from app.core.prompt_manager.version import VersionManager
from app.core.prompt_manager.safety import SafetyFilter


class PromptManager:
    """Prompt 全生命周期管理.

    用法:
        pm = PromptManager()

        # 1. 确定版本
        version = pm.version.resolve(session_id)

        # 2. 组装上下文（带元数据）
        context = pm.builder.build(chunks, mode="standard")

        # 3. 渲染最终 messages
        messages = pm.renderer.render(
            system_tpl="system/food_safety_expert.j2",
            context_mode="standard",
            user_query=safe_q,
            variables={"role": user_role, "context": context},
            version=version,
        )

        # 4. 安全检查
        safe_context, threats = pm.safety.sanitize_documents(context)
        safe_context = pm.safety.wrap_documents(safe_context)
    """

    def __init__(self, settings=None):
        if settings is None:
            from app.config import get_settings
            settings = get_settings()

        self.loader = PromptLoader(settings)
        self.version = VersionManager(settings)
        self.builder = ContextBuilder(settings)
        self.renderer = PromptRenderer(self.loader)
        self.safety = SafetyFilter(settings)


# 模块级单例
prompt_manager = PromptManager()
