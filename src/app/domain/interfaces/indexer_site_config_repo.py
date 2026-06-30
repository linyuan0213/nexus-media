"""
索引器站点配置 Repository 接口
定义纯接口，与具体 ORM 实现解耦。
"""

from typing import Protocol

from app.domain.entities.indexer_site_config import IndexerSiteConfigEntity


class IIndexerSiteConfigRepository(Protocol):
    """索引器站点配置仓储接口"""

    def upsert_site(
        self,
        site_name: str,
        source: str,
        public: bool | None = None,
        enabled: bool | None = None,
        download_setting: int | None = None,
        default_settings: dict | None = None,
    ) -> None:
        """插入或更新站点配置；不覆盖 source 字段。"""
        ...

    def get_by_name(self, site_name: str) -> IndexerSiteConfigEntity | None:
        """根据站点名获取配置"""
        ...

    def get_by_id(self, id: int | str) -> IndexerSiteConfigEntity | None:
        """根据主键 ID 获取配置"""
        ...

    def list_all(
        self, source: str | None = None, source_ne: str | None = None, enabled: bool | None = None
    ) -> list[IndexerSiteConfigEntity]:
        """获取所有配置，可按来源/排除来源/启用状态过滤"""
        ...

    def list_enabled_names(self, source: str | None = None) -> list[str]:
        """获取已启用站点名列表"""
        ...

    def update_enabled(self, site_name: str, enabled: bool) -> None:
        """更新站点启用状态"""
        ...

    def update_download_setting(self, site_name: str, download_setting: int | None) -> None:
        """更新站点下载设置"""
        ...

    def update_default_settings(self, site_name: str, default_settings: dict | None) -> None:
        """更新站点默认设置"""
        ...

    def get_download_setting(self, site_name: str) -> str | None:
        """获取站点下载设置（字符串形式），未启用或为空返回 None"""
        ...

    def migrate_from_user_indexer_sites(self, user_indexer_sites: list[int], site_name_by_id: dict[int, str]) -> None:
        """从 UserIndexerSites（CONFIG_SITE.ID 列表）迁移启用状态"""
        ...
