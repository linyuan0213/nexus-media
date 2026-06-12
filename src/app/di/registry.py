"""运行时对象注册表 — 纯字典，零框架依赖.

使用 RegistryKey 枚举替代字符串键，提供编译期类型安全.

职责：
- app/di/factories.py: 创建对象后注册
- app/di/deps.py: FastAPI Depends 获取
- api/main.py: lifespan 中启动/关闭
- tests/: 测试中 mock

禁止使用位置：
- app/services/*: Service 内部不得调用
- app/media/*: 媒体组件内部不得调用
- app/message/*: 消息组件内部不得调用
"""

from typing import Any

from app.di.types import RegistryKey


class Registry:
    """运行时对象注册表."""

    def __init__(self) -> None:
        self._store: dict[RegistryKey, Any] = {}

    def set(self, key: RegistryKey, instance: Any) -> None:
        """注册对象."""
        self._store[key] = instance

    def get(self, key: RegistryKey | str) -> Any:
        """获取对象。"""
        if isinstance(key, str):
            key = RegistryKey(key)
        if key not in self._store:
            raise KeyError(f"'{key.value}' 尚未注册。请在 app/di/factories.py 中创建并注册。")
        return self._store[key]

    def has(self, key: RegistryKey | str) -> bool:
        """检查键是否已注册。"""
        if isinstance(key, str):
            try:
                key = RegistryKey(key)
            except ValueError:
                return False
        return key in self._store

    def clear(self) -> None:
        """清空注册表."""
        self._store.clear()


# 全局实例 — 由 lifespan 控制生命周期
registry = Registry()
