"""
Site Repository 适配器
实现 ISiteRepository 接口，将 SQLAlchemy ORM 操作转换为领域实体。
"""

import json

from sqlalchemy import Integer, cast

from app.db import auto_commit
from app.db.models import CONFIGSITE, SITEFAVICON, SITESTATISTICSHISTORY, SITEUSERINFOSTATS
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.site_repository import SiteRepository
from app.domain.entities.site import SiteEntity
from app.domain.interfaces.site_repo import ISiteRepository
from app.di import container


class SiteRepositoryAdapter(ISiteRepository):
    """
    站点仓储适配器
    将现有 SiteRepository 的 ORM 操作适配为领域实体接口
    """

    def __init__(self, repo: SiteRepository | None = None):
        self._repo = repo or container.site_repository()

    def get_by_id(self, site_id: int) -> SiteEntity | None:
        """根据ID获取站点"""
        orm_list = self._repo.get_site_by_id(site_id)
        if orm_list and len(orm_list) > 0:
            return SiteEntity.from_orm(orm_list[0])
        return None

    def list_all(self) -> list[SiteEntity]:
        """获取所有站点（按优先级排序）"""
        orm_list = self._repo.get_config_site()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def list_by_name(self, name: str) -> list[SiteEntity]:
        """按名称查询站点（返回列表是为了兼容可能的重名情况）"""
        # 现有 SiteRepository 没有直接按名称查询的方法
        # 使用 list_all 后过滤
        all_sites = self.list_all()
        return [s for s in all_sites if s.name == name]

    def insert(self, entity: SiteEntity) -> None:
        """插入站点"""
        self._repo.insert_config_site(
            name=entity.name,
            site_pri=str(entity.pri),
            rssurl=entity.rss_url or "",
            signurl=entity.sign_url or "",
            cookie=entity.cookie or "",
            note=json.dumps(entity.note) if entity.note else "",
            rss_uses=entity.rss_uses or "",
        )

    def update(self, entity: SiteEntity) -> None:
        """更新站点"""
        if not entity.id:
            raise ValueError("Entity ID is required for update")
        self._repo.update_config_site(
            tid=entity.id,
            name=entity.name,
            site_pri=str(entity.pri),
            rssurl=entity.rss_url or "",
            signurl=entity.sign_url or "",
            cookie=entity.cookie or "",
            note=json.dumps(entity.note) if entity.note else "",
            rss_uses=entity.rss_uses or "",
        )

    def delete(self, site_id: int) -> None:
        """删除站点"""
        self._repo.delete_config_site(site_id)

    def update_cookie_ua(self, site_id: int, cookie: str, ua: str | None = None) -> None:
        """更新站点Cookie和UA"""
        self._repo.update_site_cookie_ua(site_id, cookie, ua)

    def get_site_user_statistics(self, strict_urls: list | None = None, num: int = 100) -> list[SITEUSERINFOSTATS]:
        return self._repo.get_site_user_statistics(strict_urls=strict_urls, num=num)

    def update_site_user_statistics(self, site_user_infos: list) -> None:
        self._repo.update_site_user_statistics(site_user_infos)

    def update_site_favicon(self, site_user_infos: list) -> None:
        self._repo.update_site_favicon(site_user_infos)

    def update_site_seed_info(self, site_user_infos: list) -> None:
        self._repo.update_site_seed_info(site_user_infos)

    def get_site_user_seeding_info(self, site: str) -> tuple | None:
        return self._repo.get_site_seeding_info(site=site)

    def get_config_site(self) -> list[CONFIGSITE]:
        return self._repo.get_config_site()

    def get_site_favicons(self) -> list[SITEFAVICON]:
        return self._repo.get_site_favicons()

    def insert_config_site(
        self,
        name: str,
        site_pri: str,
        rssurl: str | None = None,
        signurl: str | None = None,
        cookie: str | None = None,
        note: str | None = None,
        rss_uses: str | None = None,
    ) -> None:
        return self._repo.insert_config_site(
            name=name, site_pri=site_pri, rssurl=rssurl, signurl=signurl, cookie=cookie, note=note, rss_uses=rss_uses
        )

    def update_config_site(
        self,
        tid: int | None,
        name: str,
        site_pri: str,
        rssurl: str,
        signurl: str,
        cookie: str,
        note: str,
        rss_uses: str,
    ) -> None:
        return self._repo.update_config_site(
            tid=tid,
            name=name,
            site_pri=site_pri,
            rssurl=rssurl,
            signurl=signurl,
            cookie=cookie,
            note=note,
            rss_uses=rss_uses,
        )

    def delete_config_site(self, siteid: int | None) -> None:
        return self._repo.delete_config_site(siteid)

    def update_config_site_note(self, tid: int | None, note: str) -> None:
        return self._repo.update_config_site_note(tid=tid, note=note)

    def get_site_by_id(self, tid: int) -> list[CONFIGSITE]:
        return self._repo.get_site_by_id(tid=tid)

    def insert_site_statistics_history(self, site_user_infos: list) -> None:
        self._repo.insert_site_statistics_history(site_user_infos)

    def get_site_statistics_recent_sites(
        self, days: int, end_day: str | None = None, strict_urls: list | None = None
    ) -> tuple[int, int, list, list, list]:
        return self._repo.get_site_statistics_recent_sites(days=days, end_day=end_day, strict_urls=strict_urls)

    def get_site_statistics_history(self, site: str, days: int = 730) -> list[SITESTATISTICSHISTORY]:
        return self._repo.get_site_statistics_history(site=site, days=days)

    def get_site_seeding_info(self, site: str) -> tuple | None:
        return self._repo.get_site_seeding_info(site=site)

    def update_site_user_statistics_site_name(self, new_name: str, old_name: str) -> None:
        self._repo.update_site_user_statistics_site_name(new_name, old_name)

    def update_site_seed_info_site_name(self, new_name: str, old_name: str) -> None:
        self._repo.update_site_seed_info_site_name(new_name, old_name)

    def update_site_statistics_site_name(self, new_name: str, old_name: str) -> None:
        self._repo.update_site_statistics_site_name(new_name, old_name)


class SiteRepositoryImpl(BaseRepository):
    """
    纯领域仓储实现（可选，用于完全替换 container.sites() 单例时）
    当前阶段仅作演示，实际业务仍通过 Adapter 调用旧 Repository
    """

    def get_by_id(self, site_id: int) -> SiteEntity | None:
        orm = self._db.query(CONFIGSITE).filter(int(site_id) == CONFIGSITE.ID).first()
        return SiteEntity.from_orm(orm) if orm else None

    def list_all(self) -> list[SiteEntity]:

        orm_list = self._db.query(CONFIGSITE).order_by(cast(CONFIGSITE.PRI, Integer).asc()).all()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def list_by_name(self, name: str) -> list[SiteEntity]:
        orm_list = self._db.query(CONFIGSITE).filter(name == CONFIGSITE.NAME).all()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def insert(self, entity: SiteEntity) -> None:

        @auto_commit(self._db)
        def _do_insert():
            self._db.insert(
                CONFIGSITE(
                    NAME=entity.name,
                    PRI=entity.pri,
                    RSSURL=entity.rss_url,
                    SIGNURL=entity.sign_url,
                    COOKIE=entity.cookie,
                    NOTE=json.dumps(entity.note) if entity.note else None,
                    INCLUDE=entity.rss_uses,
                )
            )

        _do_insert()

    def update(self, entity: SiteEntity) -> None:
        if not entity.id:
            raise ValueError("Entity ID is required")

        @auto_commit(self._db)
        def _do_update():
            self._db.query(CONFIGSITE).filter(int(entity.id) == CONFIGSITE.ID).update(
                {
                    "NAME": entity.name,
                    "PRI": entity.pri,
                    "RSSURL": entity.rss_url,
                    "SIGNURL": entity.sign_url,
                    "COOKIE": entity.cookie,
                    "NOTE": json.dumps(entity.note) if entity.note else None,
                    "INCLUDE": entity.rss_uses,
                }
            )

        _do_update()

    def delete(self, site_id: int) -> None:

        @auto_commit(self._db)
        def _do_delete():
            self._db.query(CONFIGSITE).filter(int(site_id) == CONFIGSITE.ID).delete()

        _do_delete()

    def update_cookie_ua(self, site_id: int, cookie: str, ua: str | None = None) -> None:

        @auto_commit(self._db)
        def _do_update():
            rec = self._db.query(CONFIGSITE).filter(int(site_id) == CONFIGSITE.ID).first()
            if rec:
                note = {}
                if rec.NOTE:
                    try:
                        note = json.loads(rec.NOTE)
                    except Exception:
                        note = {}
                if ua:
                    note["ua"] = ua
                self._db.query(CONFIGSITE).filter(int(site_id) == CONFIGSITE.ID).update(
                    {"COOKIE": cookie, "NOTE": json.dumps(note)}
                )

        _do_update()
