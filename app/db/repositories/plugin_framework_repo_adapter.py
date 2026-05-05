# -*- coding: utf-8 -*-
"""
Plugin Framework v2 Repository 适配器
将 PluginFrameworkRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.plugin import (
    PluginManifestEntity, PluginConfigEntity, PluginLogEntity,
)
from app.domain.interfaces.plugin_repo import (
    IPluginManifestRepository, IPluginConfigRepository, IPluginLogRepository,
)
from app.db.repositories.plugin_framework_repository import PluginFrameworkRepository


class PluginManifestRepositoryAdapter(IPluginManifestRepository):
    """插件清单仓储适配器"""

    def __init__(self, repo: Optional[PluginFrameworkRepository] = None):
        self._repo = repo or PluginFrameworkRepository()

    def get_all(self) -> List[PluginManifestEntity]:
        rows = self._repo.get_all_manifests()
        return [e for e in [PluginManifestEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, plugin_id: str) -> Optional[PluginManifestEntity]:
        row = self._repo.get_manifest_by_id(plugin_id)
        return PluginManifestEntity.from_orm(row) if row else None

    def insert(self, entity: PluginManifestEntity) -> bool:
        return self._repo.insert_manifest(entity)

    def update(self, entity: PluginManifestEntity) -> bool:
        return self._repo.update_manifest(entity)

    def delete(self, plugin_id: str) -> bool:
        return self._repo.delete_manifest(plugin_id)

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        return self._repo.set_manifest_enabled(plugin_id, enabled)


class PluginConfigRepositoryAdapter(IPluginConfigRepository):
    """插件配置仓储适配器"""

    def __init__(self, repo: Optional[PluginFrameworkRepository] = None):
        self._repo = repo or PluginFrameworkRepository()

    def get(self, plugin_id: str) -> Optional[PluginConfigEntity]:
        row = self._repo.get_config(plugin_id)
        return PluginConfigEntity.from_orm(row) if row else None

    def save(self, entity: PluginConfigEntity) -> bool:
        return self._repo.save_config(entity)

    def delete(self, plugin_id: str) -> bool:
        return self._repo.delete_config(plugin_id)


class PluginLogRepositoryAdapter(IPluginLogRepository):
    """插件日志仓储适配器"""

    def __init__(self, repo: Optional[PluginFrameworkRepository] = None):
        self._repo = repo or PluginFrameworkRepository()

    def insert(self, plugin_id: str, level: str, message: str) -> bool:
        return self._repo.insert_log(plugin_id, level, message)

    def get_by_plugin(self, plugin_id: str, page: int = 1, page_size: int = 20) -> List[PluginLogEntity]:
        rows = self._repo.get_logs_by_plugin(plugin_id, page, page_size)
        return [e for e in [PluginLogEntity.from_orm(r) for r in rows] if e is not None]

    def count_by_plugin(self, plugin_id: str) -> int:
        return self._repo.count_logs_by_plugin(plugin_id)

    def clear_by_plugin(self, plugin_id: str) -> bool:
        return self._repo.clear_logs_by_plugin(plugin_id)
