"""
IndexerConfigRepository Adapter
适配 IndexerConfigRepository 到 IIndexerConfigRepository 接口。
"""

from app.db.repositories.indexer_config_repository import IndexerConfigRepository
from app.domain.entities.indexer_config import IndexerConfigEntity
from app.domain.interfaces.indexer_config_repo import IIndexerConfigRepository


class IndexerConfigRepositoryAdapter(IIndexerConfigRepository):
    """索引器配置仓储适配器"""

    def __init__(self, repo: IndexerConfigRepository | None = None):
        self._repo = repo or IndexerConfigRepository()

    def get_by_client_id(self, client_id: str) -> IndexerConfigEntity | None:
        row = self._repo.get_by_client_id(client_id)
        if row is None:
            return None
        return IndexerConfigEntity(**row)

    def get_all(self) -> list[IndexerConfigEntity]:
        return [IndexerConfigEntity(**r) for r in self._repo.get_all()]

    def upsert(self, client_id: str, enabled: bool | None = None, config: dict | None = None) -> None:
        self._repo.upsert(client_id=client_id, enabled=enabled, config=config)
