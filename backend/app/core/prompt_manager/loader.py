"""Prompt 模板加载器 — Jinja2 模板发现 + 缓存 + 热重载."""
import time
import threading
from pathlib import Path
from typing import Optional


class TemplateCache:
    """线程安全的模板内容缓存."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, path: str) -> Optional[str]:
        with self._lock:
            entry = self._store.get(path)
            if entry is None:
                return None
            return entry[0]

    def set(self, path: str, content: str):
        with self._lock:
            self._store[path] = (content, time.time())

    def invalidate(self, path: str):
        with self._lock:
            self._store.pop(path, None)

    def clear(self):
        with self._lock:
            self._store.clear()


class PromptLoader:
    """从 prompts/ 目录加载 Jinja2 模板.

    特性:
        - 按版本切换: 优先读 versions/{version}/，fallback 到 DEFAULT_PROMPT_VERSION
        - 热重载: PROMPT_HOT_RELOAD=true 时每次检查文件变更
        - 生产缓存: PROMPT_HOT_RELOAD=false 时使用内存缓存
    """

    def __init__(self, settings):
        self._settings = settings
        self._prompt_dir = Path(settings.prompt_dir) if hasattr(settings, 'prompt_dir') else (
            Path(__file__).parent.parent.parent / "prompts"
        )
        self._hot_reload = getattr(settings, "prompt_hot_reload", False)
        self._cache = TemplateCache()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def load(self, template_path: str, version: Optional[str] = None) -> str:
        """加载指定模板的原始内容.

        Args:
            template_path: 相对于 prompts/ 的路径，如 "system/food_safety_expert.j2"
            version: 版本号如 "v1.0.0"，为 None 时使用默认版本

        Returns:
            模板文件内容字符串
        """
        resolved = self._resolve_path(template_path, version)
        return self._read(resolved)

    def load_system_prompt(
        self,
        template_path: str = "system/food_safety_expert.j2",
        version: Optional[str] = None,
    ) -> str:
        """便捷方法: 加载 System Prompt 模板."""
        return self.load(template_path, version)

    def load_context_template(
        self,
        mode: str = "standard",
        version: Optional[str] = None,
    ) -> str:
        """便捷方法: 加载上下文组装模板."""
        mode_map = {
            "standard": "context/standard.j2",
            "citation": "context/citation.j2",
            "compact": "context/compact.j2",
        }
        filename = mode_map.get(mode, f"context/{mode}.j2")
        return self.load(filename, version)

    def load_user_template(
        self,
        template_path: str = "user/default.j2",
        version: Optional[str] = None,
    ) -> str:
        """便捷方法: 加载用户消息模板."""
        return self.load(template_path, version)

    def invalidate_cache(self, template_path: Optional[str] = None):
        """清除缓存。不传参数则清空全部缓存."""
        if template_path is None:
            self._cache.clear()
        else:
            self._cache.invalidate(template_path)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _resolve_path(self, template_path: str, version: Optional[str]) -> Path:
        """解析模板文件实际路径，含版本 fallback.

        Fallback 链:
            1. versions/{requested_version}/template_path
            2. versions/{DEFAULT_PROMPT_VERSION}/template_path
            3. prompts/template_path (根目录)
        """
        # 1. 请求的版本目录
        if version:
            versioned = self._prompt_dir / "versions" / version / template_path
            if versioned.exists():
                return versioned

        # 2. 默认版本目录
        default_version = self._get_default_version()
        if default_version and default_version != version:
            versioned = self._prompt_dir / "versions" / default_version / template_path
            if versioned.exists():
                return versioned

        # 3. prompts/ 根目录
        fallback = self._prompt_dir / template_path
        if fallback.exists():
            return fallback

        searched = []
        if version:
            searched.append(f"versions/{version}/{template_path}")
        if default_version:
            searched.append(f"versions/{default_version}/{template_path}")
        searched.append(template_path)
        raise FileNotFoundError(
            f"模板文件不存在: 已查找 {', '.join(searched)}"
        )

    def _get_default_version(self) -> Optional[str]:
        """从配置读取默认版本."""
        version = getattr(self._settings, "default_prompt_version", None)
        if version and (self._prompt_dir / "versions" / version).exists():
            return version
        return None

    def _read(self, filepath: Path) -> str:
        """读取文件内容，根据 hot_reload 决定缓存策略."""
        path_str = str(filepath)

        if self._hot_reload:
            return filepath.read_text(encoding="utf-8")

        # 生产模式: 缓存优先
        cached = self._cache.get(path_str)
        if cached is not None:
            return cached

        content = filepath.read_text(encoding="utf-8")
        self._cache.set(path_str, content)
        return content
