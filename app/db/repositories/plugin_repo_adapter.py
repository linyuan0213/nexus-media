# -*- coding: utf-8 -*-
"""
Plugin 领域 Repository 适配器
将旧版 PluginRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.plugin import PluginHistoryEntity, TmdbBlacklistEntity
from app.domain.interfaces.plugin_repo import IPluginHistoryRepository, ITmdbBlacklistRepository
from app.db.repositories.plugin_repository import PluginRepository


class PluginHistoryRepositoryAdapter(IPluginHistoryRepository):
    """插件历史仓储适配器"""

    def __init__(self, repo: Optional[PluginRepository] = None):
        self._repo = repo or PluginRepository()

    def insert_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        return self._repo.insert_plugin_history(plugin_id, key, value)

    def get_plugin_history(self, plugin_id: str, key: Optional[str] = None) -> List[PluginHistoryEntity]:
        rows = self._repo.get_plugin_history(plugin_id, key)
        if rows is None:
            return []
        if not isinstance(rows, list):
            rows = [rows]
        return [e for e in [PluginHistoryEntity.from_orm(r) for r in rows] if e is not None]

    def update_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        return self._repo.update_plugin_history(plugin_id, key, value)

    def delete_plugin_history(self, plugin_id: str, key: str) -> bool:
        return self._repo.delete_plugin_history(plugin_id, key)


class TmdbBlacklistRepositoryAdapter(ITmdbBlacklistRepository):
    """TMDB黑名单仓储适配器"""

    def __init__(self, repo: Optional[PluginRepository] = None):
        self._repo = repo or PluginRepository()

    def is_tmdb_blacklisted(self, tmdb_id: str, media_type: Optional[str] = None) -> bool:
        return self._repo.is_tmdb_blacklisted(tmdb_id, media_type)

    def get_tmdb_blacklist(self) -> List[TmdbBlacklistEntity]:
        rows = self._repo.get_tmdb_blacklist()
        return [e for e in [TmdbBlacklistEntity.from_orm(r) for r in rows] if e is not None]

    def insert_tmdb_blacklist(self, tmdb_id: str, title: Optional[str] = None,
                               year: Optional[str] = None, media_type: Optional[str] = None,
                               poster_path: Optional[str] = None, backdrop_path: Optional[str] = None,
                               note: Optional[str] = None) -> bool:
        return self._repo.insert_tmdb_blacklist(tmdb_id, title, year, media_type, poster_path, backdrop_path, note)

    def delete_tmdb_blacklist(self, tmdb_id: str, media_type: Optional[str] = None) -> bool:
        return self._repo.delete_tmdb_blacklist(tmdb_id, media_type)

    def clear_tmdb_blacklist(self) -> bool:
        return self._repo.clear_tmdb_blacklist()
