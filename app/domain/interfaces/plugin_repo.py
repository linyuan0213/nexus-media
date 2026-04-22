# -*- coding: utf-8 -*-
"""
插件历史 / TMDB黑名单仓储接口
"""
from typing import List, Optional, Protocol

from app.domain.entities.plugin import PluginHistoryEntity, TmdbBlacklistEntity


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
