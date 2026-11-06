"""
插件历史 / 识别黑名单仓储接口 / 插件框架v2仓储接口
"""

from typing import Protocol

from app.domain.entities.plugin import (
    MetadataBlacklistEntity,
    PluginConfigEntity,
    PluginHistoryEntity,
    PluginLogEntity,
    PluginManifestEntity,
)


class IPluginHistoryRepository(Protocol):
    """插件历史仓储接口"""

    def insert_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        """新增插件运行记录"""
        ...

    def get_plugin_history(self, plugin_id: str, key: str | None = None) -> list[PluginHistoryEntity]:
        """查询插件运行记录"""
        ...

    def update_plugin_history(self, plugin_id: str, key: str, value: str) -> bool:
        """更新插件运行记录"""
        ...

    def delete_plugin_history(self, plugin_id: str, key: str) -> bool:
        """删除插件运行记录"""
        ...


class IMetadataBlacklistRepository(Protocol):
    """识别黑名单仓储接口."""

    def is_blacklisted(self, provider: str, external_id: str, media_type: str | None = None) -> bool:
        """检查 provider 引用是否在黑名单中."""
        ...

    def get_blacklist(self, provider: str | None = None) -> list[MetadataBlacklistEntity]:
        """获取识别黑名单记录."""
        ...

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
        """添加到识别黑名单."""
        ...

    def delete_blacklist(self, provider: str, external_id: str, media_type: str | None = None) -> bool:
        """从识别黑名单删除."""
        ...

    def clear_blacklist(self, provider: str | None = None) -> bool:
        """清空识别黑名单记录."""
        ...


class IPluginManifestRepository(Protocol):
    """插件框架v2 - 插件清单仓储接口"""

    def get_all(self) -> list[PluginManifestEntity]:
        """获取所有已安装插件"""
        ...

    def get_by_id(self, plugin_id: str) -> PluginManifestEntity | None:
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

    def get(self, plugin_id: str) -> PluginConfigEntity | None:
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

    def get_by_plugin(self, plugin_id: str, page: int = 1, page_size: int = 20) -> list[PluginLogEntity]:
        """分页获取插件日志"""
        ...

    def count_by_plugin(self, plugin_id: str) -> int:
        """统计插件日志数量"""
        ...

    def clear_by_plugin(self, plugin_id: str) -> bool:
        """清空插件日志"""
        ...
