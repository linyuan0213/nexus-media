"""外部依赖连通性目标契约."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectivityTarget:
    """一个可测试的外部依赖目标，由 provider/插件声明."""

    key: str
    label: str
    url: str
    category: str = "external"
    requires_auth: bool = False
    probe: str = "http"
    use_proxy: bool = False
    probe_fn: Callable[[], None] | None = None
    order: int = 100

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "target": self.key,
            "label": self.label,
            "url": self.url,
            "category": self.category,
            "requires_auth": self.requires_auth,
            "use_proxy": self.use_proxy,
            "order": self.order,
        }
