"""插件市场源契约（domain）."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class MarketSource:
    """市场源"""

    name: str
    url: str
    enabled: bool = True
    auto_update: bool = False
    public_key: str = ""
    last_sync_at: str = ""
    last_error: str = ""
    source_id: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id or self.name,
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "auto_update": self.auto_update,
            "public_key": self.public_key,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
        }


class PluginMarketStore(Protocol):
    """市场源存储抽象（DB 仓库或内存实现）."""

    def list(self) -> list[MarketSource]: ...

    def add(self, source: MarketSource) -> MarketSource: ...

    def update(self, source: MarketSource) -> MarketSource: ...

    def delete(self, source_id: str) -> bool: ...
