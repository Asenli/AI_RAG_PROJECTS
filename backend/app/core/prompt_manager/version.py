"""版本控制 — 文件系统版本发现 + session_id 哈希分流."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class VersionInfo:
    """版本元数据."""
    name: str
    path: Path
    is_default: bool = False


class VersionManager:
    """Prompt 版本管理器.

    职责:
        1. 发现 prompts/versions/ 下所有可用版本
        2. 根据 session_id 哈希决定使用哪个版本（A/B 测试）
        3. 支持配置回滚（DEFAULT_PROMPT_VERSION 切换即可）

    A/B 分流逻辑:
        bucket = hash(session_id) % 100
        if bucket < AB_TEST_TRAFFIC_PERCENT → 实验版本
        else → 默认版本
    """

    def __init__(self, settings):
        self._settings = settings
        self._prompt_dir = Path(settings.prompt_dir) if hasattr(settings, 'prompt_dir') else (
            Path(__file__).parent.parent.parent / "prompts"
        )
        self._versions_dir = self._prompt_dir / "versions"

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def resolve(self, session_id: str) -> str:
        """根据 session_id 决定使用的 Prompt 版本.

        Returns:
            版本号字符串，如 "v1.0.0"
        """
        default_version = getattr(
            self._settings, "default_prompt_version", "v1.0.0"
        )

        # A/B 测试未启用 → 直接返回默认版本
        if not getattr(self._settings, "ab_test_enabled", False):
            return default_version

        new_version = getattr(self._settings, "ab_test_new_version", "")
        traffic_pct = getattr(self._settings, "ab_test_traffic_percent", 0)

        if not new_version or traffic_pct <= 0:
            return default_version

        # 哈希分流
        bucket = self._hash_bucket(session_id)
        if bucket < traffic_pct:
            if self._version_exists(new_version):
                return new_version
            return default_version

        return default_version

    def list_versions(self) -> list[VersionInfo]:
        """列出所有可用版本."""
        if not self._versions_dir.exists():
            return []

        default_name = getattr(
            self._settings, "default_prompt_version", "v1.0.0"
        )
        versions = []
        for d in sorted(self._versions_dir.iterdir()):
            if d.is_dir():
                versions.append(VersionInfo(
                    name=d.name,
                    path=d,
                    is_default=(d.name == default_name),
                ))
        return versions

    def version_exists(self, version: str) -> bool:
        """检查指定版本是否存在."""
        return self._version_exists(version)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _version_exists(self, version: str) -> bool:
        return (self._versions_dir / version).is_dir()

    @staticmethod
    def _hash_bucket(session_id: str) -> int:
        """将 session_id 哈希到 0-99 的桶."""
        if not session_id:
            return 0
        h = hashlib.md5(session_id.encode("utf-8")).hexdigest()
        return int(h[:8], 16) % 100
