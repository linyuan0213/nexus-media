"""
索引器配置领域接口
"""

from abc import ABC, abstractmethod

from app.domain.entities.indexer_config import IndexerConfigEntity


class IIndexerConfigRepository(ABC):
    """索引器配置仓储抽象接口"""

    @abstractmethod
    def get_by_client_id(self, client_id: str) -> IndexerConfigEntity | None: ...

    @abstractmethod
    def get_all(self) -> list[IndexerConfigEntity]: ...

    @abstractmethod
    def upsert(self, client_id: str, enabled: bool | None = None, config: dict | None = None) -> None: ...
