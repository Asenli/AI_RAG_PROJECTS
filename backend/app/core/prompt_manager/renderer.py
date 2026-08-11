"""模板渲染器 — Jinja2 渲染引擎，输出标准 ChatCompletion Message 格式."""
from __future__ import annotations
from typing import Optional, Any
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from app.core.prompt_manager.loader import PromptLoader


class PromptRenderer:
    """Jinja2 渲染器，负责将模板 + 变量 → OpenAI Message 格式.

    用法:
        renderer = PromptRenderer(loader)
        messages = renderer.render(
            system_tpl="system/food_safety_expert.j2",
            context="...",
            user_query="食堂怎么采购食材？",
            variables={
                "role": "canteen",
                "school_name": "第一中学",
                "conversation_history": "...",
            },
        )
        # 返回:
        # [
        #     {"role": "system", "content": "你是..."},
        #     {"role": "user", "content": "食堂怎么采购食材？"},
        # ]
    """

    def __init__(self, loader: PromptLoader):
        self._loader = loader
        self._env_cache: dict[str, Environment] = {}

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def render(
        self,
        system_tpl: str = "system/food_safety_expert.j2",
        user_tpl: str = "user/default.j2",
        context: str = "",
        context_mode: str = "standard",
        user_query: str = "",
        variables: Optional[dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """渲染完整对话 messages.

        Returns:
            OpenAI ChatCompletion 格式的 messages 列表
        """
        variables = variables or {}

        # 渲染 System Prompt
        system_content = self._render_template(
            system_tpl,
            {
                **variables,
                "context": context,
                "context_mode": context_mode,
            },
            version,
        )

        # 渲染 User Message
        user_content = self._render_template(
            user_tpl,
            {
                **variables,
                "user_query": user_query,
                "context": context,
            },
            version,
        )

        return [
            {"role": "system", "content": system_content.strip()},
            {"role": "user", "content": user_content.strip()},
        ]

    def render_system_only(
        self,
        template_path: str = "system/food_safety_expert.j2",
        variables: Optional[dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> str:
        """仅渲染 System Prompt（用于意图分类等场景）."""
        return self._render_template(
            template_path,
            variables or {},
            version,
        ).strip()

    def render_intent_classifier(
        self,
        template_path: str = "classifier/intent_v1.j2",
        user_query: str = "",
        user_role: str = "",
        version: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """便捷方法: 渲染意图分类器的 messages."""
        system_content = self._render_template(
            template_path,
            {"user_role": user_role},
            version,
        ).strip()

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"用户角色：{user_role}\n用户输入：{user_query}"},
        ]

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _render_template(
        self,
        template_path: str,
        variables: dict[str, Any],
        version: Optional[str] = None,
    ) -> str:
        """加载模板 → Jinja2 渲染."""
        template_source = self._loader.load(template_path, version=version)

        # 给模板提供 FileSystemLoader 支持 {% include %}，同时用 from_string 渲染
        env = self._get_env()
        template = env.from_string(template_source)
        return template.render(**variables)

    def _get_env(self) -> Environment:
        """获取 Jinja2 Environment."""
        prompt_dir = self._loader._prompt_dir

        # 用缓存 key 避免重复创建 Environment
        cache_key = str(prompt_dir)
        if cache_key not in self._env_cache:
            self._env_cache[cache_key] = Environment(
                loader=FileSystemLoader([str(prompt_dir)]),
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._env_cache[cache_key]
