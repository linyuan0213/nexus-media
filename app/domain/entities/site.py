"""
站点领域实体
映射 ORM 模型为纯数据结构，与 SQLAlchemy 解耦。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SiteEntity:
    """站点配置领域实体"""

    id: int = 0
    name: str = ""
    pri: int = 0
    rss_url: str | None = None
    sign_url: str | None = None
    cookie: str | None = None
    note: dict[str, Any] = field(default_factory=dict)
    rss_uses: str | None = None

    @classmethod
    def from_orm(cls, orm_obj) -> "SiteEntity":
        """从 ORM 对象转换（兼容 CONFIGSITE 模型）"""
        if orm_obj is None:
            return cls()
        import json

        note_raw = getattr(orm_obj, "NOTE", None)
        note = {}
        if note_raw:
            try:
                note = json.loads(note_raw) if isinstance(note_raw, str) else dict(note_raw)
            except Exception:
                note = {}
        return cls(
            id=getattr(orm_obj, "ID", 0) or 0,
            name=getattr(orm_obj, "NAME", "") or "",
            pri=int(getattr(orm_obj, "PRI", 0) or 0),
            rss_url=getattr(orm_obj, "RSSURL", None),
            sign_url=getattr(orm_obj, "SIGNURL", None),
            cookie=getattr(orm_obj, "COOKIE", None),
            note=note,
            rss_uses=getattr(orm_obj, "INCLUDE", None),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为兼容现有 container.sites() 返回格式的 dict"""
        return {
            "id": self.id,
            "name": self.name,
            "pri": self.pri,
            "rssurl": self.rss_url,
            "signurl": self.sign_url,
            "cookie": self.cookie,
            "note": self.note,
            "rss_uses": self.rss_uses,
        }


@dataclass
class SiteStatisticsEntity:
    """站点统计领域实体"""

    id: int = 0
    site: str = ""
    date: str = ""
    user_level: str = ""
    upload: int = 0
    download: int = 0
    ratio: float = 0.0
    seeding: int = 0
    leeching: int = 0
    seeding_size: int = 0
    bonus: float = 0.0
    url: str = ""

    @classmethod
    def from_orm(cls, orm_obj) -> "SiteStatisticsEntity":
        """从 ORM 对象转换（兼容 SITESTATISTICSHISTORY / SITEUSERINFOSTATS 模型）"""
        if orm_obj is None:
            return cls()
        return cls(
            id=getattr(orm_obj, "ID", 0) or 0,
            site=getattr(orm_obj, "SITE", "") or "",
            date=getattr(orm_obj, "DATE", "") or "",
            user_level=getattr(orm_obj, "USER_LEVEL", "") or "",
            upload=getattr(orm_obj, "UPLOAD", 0) or 0,
            download=getattr(orm_obj, "DOWNLOAD", 0) or 0,
            ratio=float(getattr(orm_obj, "RATIO", 0.0) or 0.0),
            seeding=int(getattr(orm_obj, "SEEDING", 0) or 0),
            leeching=int(getattr(orm_obj, "LEECHING", 0) or 0),
            seeding_size=int(getattr(orm_obj, "SEEDING_SIZE", 0) or 0),
            bonus=float(getattr(orm_obj, "BONUS", 0.0) or 0.0),
            url=getattr(orm_obj, "URL", "") or "",
        )


@dataclass
class SiteSeedingEntity:
    """站点做种信息领域实体"""

    site: str = ""
    seeding_info: str = ""
    update_at: str = ""
    url: str = ""

    @classmethod
    def from_orm(cls, orm_obj) -> "SiteSeedingEntity":
        if orm_obj is None:
            return cls()
        return cls(
            site=getattr(orm_obj, "SITE", "") or "",
            seeding_info=getattr(orm_obj, "SEEDING_INFO", "") or "",
            update_at=getattr(orm_obj, "UPDATE_AT", "") or "",
            url=getattr(orm_obj, "URL", "") or "",
        )
