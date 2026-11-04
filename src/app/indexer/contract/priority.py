"""索引器优先级装饰器.

优先级只在这一层注入：设置来源（内置 pri / 站点配置 / 插件默认）与 provider 实现解耦。
数值越小优先级越高。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .models import IndexerHealth, IndexerInfo, IndexerPage, IndexerQuery

DEFAULT_PRIORITY = 100


class PriorityProvider:
    """给任意 provider 的站点与结果注入统一 priority 字段。"""

    def __init__(
        self,
        provider: Any,
        priorities: Mapping[str, int] | None = None,
        default: int = DEFAULT_PRIORITY,
    ):
        self._provider = provider
        self._priorities = {str(key): int(value) for key, value in (priorities or {}).items()}
        self._default = int(default)

    @property
    def provider_id(self) -> str:
        return str(getattr(self._provider, "provider_id", ""))

    def priority_for(self, site: str) -> int:
        return self._priorities.get(str(site), self._default)

    def info(self) -> IndexerInfo:
        info = self._provider.info()
        sites = tuple(replace(site, priority=self.priority_for(site.id or site.name)) for site in info.sites)
        return replace(info, sites=sites)

    def health(self) -> IndexerHealth:
        return self._provider.health()

    def search(self, query: IndexerQuery) -> IndexerPage:
        return self._annotate(self._provider.search(query))

    def list(self, query: IndexerQuery) -> IndexerPage:
        return self._annotate(self._provider.list(query))

    def close(self) -> None:
        close = getattr(self._provider, "close", None)
        if callable(close):
            close()

    def _annotate(self, page: IndexerPage) -> IndexerPage:
        items = [replace(item, priority=self.priority_for(item.site)) for item in page.items]
        return replace(page, items=items)
