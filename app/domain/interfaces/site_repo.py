"""
站点 Repository 接口
定义纯接口，与具体 ORM 实现解耦。
"""

from typing import Protocol

from app.domain.entities.site import SiteEntity, SiteSeedingEntity, SiteStatisticsEntity


class ISiteRepository(Protocol):
    """站点配置仓储接口"""

    def get_by_id(self, site_id: int) -> SiteEntity | None:
        """根据ID获取站点"""
        ...

    def list_all(self) -> list[SiteEntity]:
        """获取所有站点（按优先级排序）"""
        ...

    def list_by_name(self, name: str) -> list[SiteEntity]:
        """按名称查询站点"""
        ...

    def insert(self, entity: SiteEntity) -> None:
        """插入站点"""
        ...

    def update(self, entity: SiteEntity) -> None:
        """更新站点"""
        ...

    def delete(self, site_id: int) -> None:
        """删除站点"""
        ...

    def update_cookie_ua(self, site_id: int, cookie: str, ua: str | None) -> None:
        """更新站点Cookie和UA"""
        ...


class ISiteStatisticsRepository(Protocol):
    """站点统计仓储接口"""

    def get_by_site(self, site: str) -> SiteStatisticsEntity | None:
        """获取指定站点的最新统计信息"""
        ...

    def get_by_url(self, url: str) -> SiteStatisticsEntity | None:
        """根据URL获取站点统计信息"""
        ...

    def list_history(self, site: str, days: int = 30) -> list[SiteStatisticsEntity]:
        """获取站点历史统计数据"""
        ...

    def upsert(self, entity: SiteStatisticsEntity) -> None:
        """插入或更新站点统计"""
        ...


class ISiteSeedingRepository(Protocol):
    """站点做种信息仓储接口"""

    def get_by_site(self, site: str) -> SiteSeedingEntity | None:
        """获取指定站点的做种信息"""
        ...

    def get_by_url(self, url: str) -> SiteSeedingEntity | None:
        """根据URL获取做种信息"""
        ...

    def upsert(self, entity: SiteSeedingEntity) -> None:
        """插入或更新做种信息"""
        ...
