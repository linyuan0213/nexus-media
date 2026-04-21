# coding: utf-8
"""
Site Repository 适配器
实现 ISiteRepository 接口，将 SQLAlchemy ORM 操作转换为领域实体。
"""
import json
from typing import List, Optional

from app.db.repositories.site_repository import SiteRepository
from app.db.repositories.base_repository import BaseRepository
from app.db.models import CONFIGSITE
from app.domain.entities.site import SiteEntity
from app.domain.interfaces.site_repo import ISiteRepository


class SiteRepositoryAdapter(ISiteRepository):
    """
    站点仓储适配器
    将现有 SiteRepository 的 ORM 操作适配为领域实体接口
    """

    def __init__(self, repo: Optional[SiteRepository] = None):
        self._repo = repo or SiteRepository()

    def get_by_id(self, site_id: int) -> Optional[SiteEntity]:
        """根据ID获取站点"""
        orm_list = self._repo.get_site_by_id(site_id)
        if orm_list and len(orm_list) > 0:
            return SiteEntity.from_orm(orm_list[0])
        return None

    def list_all(self) -> List[SiteEntity]:
        """获取所有站点（按优先级排序）"""
        orm_list = self._repo.get_config_site()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def list_by_name(self, name: str) -> List[SiteEntity]:
        """按名称查询站点（返回列表是为了兼容可能的重名情况）"""
        # 现有 SiteRepository 没有直接按名称查询的方法
        # 使用 list_all 后过滤
        all_sites = self.list_all()
        return [s for s in all_sites if s.name == name]

    def insert(self, entity: SiteEntity) -> None:
        """插入站点"""
        self._repo.insert_config_site(
            name=entity.name,
            site_pri=entity.pri,
            rssurl=entity.rss_url,
            signurl=entity.sign_url,
            cookie=entity.cookie,
            note=json.dumps(entity.note) if entity.note else None,
            rss_uses=entity.rss_uses,
        )

    def update(self, entity: SiteEntity) -> None:
        """更新站点"""
        if not entity.id:
            raise ValueError("Entity ID is required for update")
        self._repo.update_config_site(
            tid=entity.id,
            name=entity.name,
            site_pri=entity.pri,
            rssurl=entity.rss_url,
            signurl=entity.sign_url,
            cookie=entity.cookie,
            note=json.dumps(entity.note) if entity.note else None,
            rss_uses=entity.rss_uses,
        )

    def delete(self, site_id: int) -> None:
        """删除站点"""
        self._repo.delete_config_site(site_id)

    def update_cookie_ua(self, site_id: int, cookie: str, ua: Optional[str] = None) -> None:
        """更新站点Cookie和UA"""
        self._repo.update_site_cookie_ua(site_id, cookie, ua)


class SiteRepositoryImpl(BaseRepository):
    """
    纯领域仓储实现（可选，用于完全替换 Sites() 单例时）
    当前阶段仅作演示，实际业务仍通过 Adapter 调用旧 Repository
    """

    def get_by_id(self, site_id: int) -> Optional[SiteEntity]:
        orm = self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(site_id)).first()
        return SiteEntity.from_orm(orm) if orm else None

    def list_all(self) -> List[SiteEntity]:
        from sqlalchemy import cast, Integer
        orm_list = self._db.query(CONFIGSITE) \
            .order_by(cast(CONFIGSITE.PRI, Integer).asc()).all()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def list_by_name(self, name: str) -> List[SiteEntity]:
        orm_list = self._db.query(CONFIGSITE).filter(CONFIGSITE.NAME == name).all()
        return [SiteEntity.from_orm(orm) for orm in orm_list]

    def insert(self, entity: SiteEntity) -> None:
        from app.db import DbPersist
        @DbPersist(self._db)
        def _do_insert():
            self._db.insert(CONFIGSITE(
                NAME=entity.name,
                PRI=entity.pri,
                RSSURL=entity.rss_url,
                SIGNURL=entity.sign_url,
                COOKIE=entity.cookie,
                NOTE=json.dumps(entity.note) if entity.note else None,
                INCLUDE=entity.rss_uses,
            ))
        _do_insert()

    def update(self, entity: SiteEntity) -> None:
        if not entity.id:
            raise ValueError("Entity ID is required")
        from app.db import DbPersist
        @DbPersist(self._db)
        def _do_update():
            self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(entity.id)).update({
                "NAME": entity.name,
                "PRI": entity.pri,
                "RSSURL": entity.rss_url,
                "SIGNURL": entity.sign_url,
                "COOKIE": entity.cookie,
                "NOTE": json.dumps(entity.note) if entity.note else None,
                "INCLUDE": entity.rss_uses,
            })
        _do_update()

    def delete(self, site_id: int) -> None:
        from app.db import DbPersist
        @DbPersist(self._db)
        def _do_delete():
            self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(site_id)).delete()
        _do_delete()

    def update_cookie_ua(self, site_id: int, cookie: str, ua: Optional[str] = None) -> None:
        from app.db import DbPersist
        @DbPersist(self._db)
        def _do_update():
            rec = self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(site_id)).first()
            if rec:
                note = {}
                if rec.NOTE:
                    try:
                        note = json.loads(rec.NOTE)
                    except Exception:
                        note = {}
                if ua:
                    note['ua'] = ua
                self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(site_id)).update({
                    "COOKIE": cookie,
                    "NOTE": json.dumps(note)
                })
        _do_update()
