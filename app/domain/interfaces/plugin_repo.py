# -*- coding: utf-8 -*-
"""
插件历史 / TMDB黑名单仓储接口 / 插件框架v2仓储接口
"""
from typing import List, Optional, Protocol

from app.domain.entities.plugin import (
    PluginHistoryEntity, TmdbBlacklistEntity,
    PluginManifestEntity, PluginConfigEntity, PluginLogEntity,
)


class IPluginHistoryRepository(Protocol):
    """插件历史仓储接口"""

    def insert_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        """新增插件运行记录"""
        ...

    def get_plugin_history(self, plugin_id: str, key: Optional[str] = None) -> List[PluginHistoryEntity]:
        """查询插件运行记录"""
        ...

    def update_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        """更新插件运行记录"""
        ...

    def delete_plugin_history(self, plugin_id: str, key: str) -> bool:
        """删除插件运行记录"""
        ...


class ITmdbBlacklistRepository(Protocol):
    """TMDB黑名单仓储接口"""

    def is_tmdb_blacklisted(self, tmdb_id: str, media_type: Optional[str] = None) -> bool:
        """检查TMDB ID是否在黑名单中"""
        ...

    def get_tmdb_blacklist(self) -> List[TmdbBlacklistEntity]:
        """获取所有TMDB黑名单记录"""
        ...

    def insert_tmdb_blacklist(self, tmdb_id: str, title: Optional[str] = None,
                               year: Optional[str] = None, media_type: Optional[str] = None,
                               poster_path: Optional[str] = None, backdrop_path: Optional[str] = None,
                               note: Optional[str] = None) -> bool:
        """添加到TMDB黑名单"""
        ...

    def delete_tmdb_blacklist(self, tmdb_id: str, media_type: Optional[str] = None) -> bool:
        """从TMDB黑名单删除"""
        ...

    def clear_tmdb_blacklist(self) -> bool:
        """清空所有TMDB黑名单记录"""
        ...


class IPluginManifestRepository(Protocol):
    """插件框架v2 - 插件清单仓储接口"""

    def get_all(self) -> List[PluginManifestEntity]:
        """获取所有已安装插件"""
        ...

    def get_by_id(self, plugin_id: str) -> Optional[PluginManifestEntity]:
        """根据ID获取插件"""
        ...

    def insert(self, entity: PluginManifestEntity) -> bool:
        """插入插件清单"""
        ...

    def update(self, entity: PluginManifestEntity) -> bool:
        """更新插件清单"""
        ...

    def delete(self, plugin_id: str) -> bool:
        """删除插件清单"""
        ...

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        """设置插件启用状态"""
        ...


class IPluginConfigRepository(Protocol):
    """插件框架v2 - 插件配置仓储接口"""

    def get(self, plugin_id: str) -> Optional[PluginConfigEntity]:
        """获取插件配置"""
        ...

    def save(self, entity: PluginConfigEntity) -> bool:
        """保存插件配置"""
        ...

    def delete(self, plugin_id: str) -> bool:
        """删除插件配置"""
        ...


class IPluginLogRepository(Protocol):
    """插件框架v2 - 插件日志仓储接口"""

    def insert(self, plugin_id: str, level: str, message: str) -> bool:
        """插入日志"""
        ...

    def get_by_plugin(self, plugin_id: str, page: int = 1, page_size: int = 20) -> List[PluginLogEntity]:
        """分页获取插件日志"""
        ...

    def count_by_plugin(self, plugin_id: str) -> int:
        """统计插件日志数量"""
        ...

    def clear_by_plugin(self, plugin_id: str) -> bool:
        """清空插件日志"""
        ...
