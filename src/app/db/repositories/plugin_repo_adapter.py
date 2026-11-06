"""
Plugin 领域 Repository 适配器
将旧版 PluginRepository 适配为新领域接口
"""

from app.db.repositories.plugin_repository import PluginRepository
from app.domain.entities.plugin import MetadataBlacklistEntity, PluginHistoryEntity
from app.domain.interfaces.plugin_repo import IMetadataBlacklistRepository, IPluginHistoryRepository


class PluginHistoryRepositoryAdapter(IPluginHistoryRepository):
    """插件历史仓储适配器"""

    def __init__(self, repo: PluginRepository | None = None):
        self._repo = repo or PluginRepository()

    def insert_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        return bool(self._repo.insert_plugin_history(plugin_id, key, value))

    def get_plugin_history(self, plugin_id: str, key: str | None = None) -> list[PluginHistoryEntity]:
        rows = self._repo.get_plugin_history(plugin_id, key)
        if rows is None:
            return []
        if not isinstance(rows, list):
            rows = [rows]
        return [e for e in [PluginHistoryEntity.from_orm(r) for r in rows] if e is not None]

    def update_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        return bool(self._repo.update_plugin_history(plugin_id, key, value))

    def delete_plugin_history(self, plugin_id: str, key: str) -> bool:
        return bool(self._repo.delete_plugin_history(plugin_id, key))


class MetadataBlacklistRepositoryAdapter(IMetadataBlacklistRepository):
    """识别黑名单仓储适配器"""

    def __init__(self, repo: PluginRepository | None = None):
        self._repo = repo or PluginRepository()

    def is_blacklisted(self, provider: str, external_id: str, media_type: str | None = None) -> bool:
        return bool(self._repo.is_blacklisted(provider, external_id, media_type))

    def get_blacklist(self, provider: str | None = None) -> list[MetadataBlacklistEntity]:
        rows = self._repo.get_blacklist(provider)
        return [e for e in [MetadataBlacklistEntity.from_orm(r) for r in rows] if e is not None]

    def insert_blacklist(
        self,
        provider: str,
        external_id: str,
        title: str | None = None,
        year: str | None = None,
        media_type: str | None = None,
        poster_path: str | None = None,
        backdrop_path: str | None = None,
        note: str | None = None,
    ) -> bool:
        return bool(
            self._repo.insert_blacklist(
                provider, external_id, title, year, media_type, poster_path, backdrop_path, note
            )
        )

    def delete_blacklist(self, provider: str, external_id: str, media_type: str | None = None) -> bool:
        return bool(self._repo.delete_blacklist(provider, external_id, media_type))

    def clear_blacklist(self, provider: str | None = None) -> bool:
        return bool(self._repo.clear_blacklist(provider))
