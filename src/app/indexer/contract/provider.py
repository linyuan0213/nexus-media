"""第三方/内置索引器必须实现的 provider 协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import IndexerHealth, IndexerInfo, IndexerPage, IndexerQuery


@runtime_checkable
class IndexerProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def info(self) -> IndexerInfo: ...

    def health(self) -> IndexerHealth: ...

    def search(self, query: IndexerQuery) -> IndexerPage: ...

    def list(self, query: IndexerQuery) -> IndexerPage: ...

    def close(self) -> None: ...
