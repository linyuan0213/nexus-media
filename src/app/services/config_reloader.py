"""ConfigReloader — 集中式配置热重载协调器.

职责：
1. 维护需要重建的 provider 列表及工厂函数
2. 配置变更时调用工厂重建 provider 并替换到 AppContext
3. 失败隔离：单个 provider 重建失败不影响其他
4. 可观测：每一步都记录日志
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import log
from app.core.settings import settings
from app.di.context import AppContext
from app.media.lookup.tmdb_client import TmdbClient


@dataclass(order=True)
class _ReloadStep:
    """重载步骤 — 按 priority 排序（数值越小越优先）."""

    priority: int
    name: str = field(compare=False)
    factory: Callable[[], Any] | None = field(default=None, compare=False)


class ConfigReloader:
    """集中式配置热重载协调器."""

    PRIORITY_SETTINGS = 0
    PRIORITY_INFRA = 10

    def __init__(self, context: AppContext):
        self._context = context
        self._steps: list[_ReloadStep] = []
        self._version = 0
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册需要重建的 provider 及工厂函数."""
        self.register("system_config", self.PRIORITY_SETTINGS)
        self.register("tmdb_client", self.PRIORITY_INFRA, factory=lambda: TmdbClient())

    def register(self, provider_name: str, priority: int = 100, factory: Callable[[], Any] | None = None) -> None:
        self._steps = [s for s in self._steps if s.name != provider_name]
        self._steps.append(_ReloadStep(priority, provider_name, factory))
        self._steps.sort()

    def reload(self) -> dict:
        """执行配置重载：settings.reload() + 重建注册的 provider."""
        self._version += 1
        log.info(f"[ConfigReloader]开始配置重载，版本 v{self._version}")

        results: dict[str, bool] = {}
        failed: list[str] = []

        for step in self._steps:
            try:
                if step.name == "system_config":
                    settings.reload()
                    results[step.name] = True
                    continue

                if step.factory is None:
                    continue

                new_instance = step.factory()
                object.__setattr__(self._context, step.name, new_instance)
                results[step.name] = True
                log.debug(f"[ConfigReloader][{step.priority}] {step.name} 重建成功")
            except Exception as e:
                results[step.name] = False
                failed.append(step.name)
                log.error(f"[ConfigReloader][{step.priority}] {step.name} 失败: {e}")

        if failed:
            log.warn(f"[ConfigReloader]重载完成 v{self._version}，{len(failed)}/{len(self._steps)} 失败: {failed}")
        else:
            log.info(f"[ConfigReloader]重载完成 v{self._version}，全部 {len(self._steps)} 步成功")

        return {"version": self._version, "results": results, "failed": failed}

    @property
    def version(self) -> int:
        return self._version

    @property
    def steps(self) -> list[str]:
        return [s.name for s in self._steps]
