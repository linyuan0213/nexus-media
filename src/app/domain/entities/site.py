"""
站点领域实体
映射 ORM 模型为纯数据结构，与 SQLAlchemy 解耦。
"""

import json
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
    api_key: str | None = None
    bearer_token: str | None = None
    headers: str | None = None
    note: dict[str, Any] = field(default_factory=dict)
    rss_uses: str | None = None

    @property
    def is_brush_enabled(self) -> bool:
        """站点是否开启刷流功能"""
        return bool(self.note.get("brush_enable"))

    @property
    def is_proxy_enabled(self) -> bool:
        """站点是否使用代理"""
        return bool(self.note.get("proxy"))

    @property
    def is_signin_enabled(self) -> bool:
        """站点是否开启签到"""
        return bool(self.note.get("signin_enable"))

    @property
    def is_search_enabled(self) -> bool:
        """站点是否开启搜索"""
        return bool(self.note.get("search_enable"))

    @property
    def is_rss_enabled(self) -> bool:
        """站点是否配置RSS"""
        return bool(self.rss_url)

    @property
    def is_active(self) -> bool:
        """站点是否可用（有认证信息且至少启用一项功能）"""
        has_auth = bool(self.cookie or self.api_key or self.bearer_token)
        return has_auth and (
            self.is_brush_enabled or self.is_signin_enabled or self.is_search_enabled or self.is_rss_enabled
        )

    @property
    def ua(self) -> str | None:
        """获取站点UA"""
        return self.note.get("ua") or None

    @property
    def parsed_headers(self) -> dict[str, Any] | None:
        """解析站点自定义请求头（独立字段优先，兼容旧配置）"""
        raw = self.headers
        if not raw:
            raw = self.note.get("headers")
        if not raw:
            return None
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            return None

    @classmethod
    def from_orm(cls, orm_obj) -> "SiteEntity":
        """从 ORM 对象转换（兼容 CONFIGSITE 模型）"""
        if orm_obj is None:
            return cls()
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
            api_key=getattr(orm_obj, "API_KEY", None),
            bearer_token=getattr(orm_obj, "BEARER_TOKEN", None),
            headers=getattr(orm_obj, "HEADERS", None),
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
            "api_key": self.api_key,
            "bearer_token": self.bearer_token,
            "headers": self.headers,
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

    @property
    def computed_ratio(self) -> float:
        """根据上传下载量计算分享率"""
        if self.download <= 0:
            return float("inf") if self.upload > 0 else 0.0
        return round(self.upload / self.download, 2)

    @property
    def ratio_display(self) -> str:
        """分享率展示文本"""
        r = self.computed_ratio
        if r == float("inf"):
            return "∞"
        return f"{r:.2f}"

    @property
    def upload_gb(self) -> float:
        """上传量GB"""
        return round(self.upload / (1024**3), 2)

    @property
    def download_gb(self) -> float:
        """下载量GB"""
        return round(self.download / (1024**3), 2)

    @property
    def seeding_size_gb(self) -> float:
        """做种体积GB"""
        return round(self.seeding_size / (1024**3), 2)

    @property
    def is_good_ratio(self) -> bool:
        """分享率是否良好（≥1.0）"""
        return self.computed_ratio >= 1.0

    @property
    def is_hnr_risk(self) -> bool:
        """是否有H&R风险（分享率<0.5且下载量>1GB）"""
        return self.computed_ratio < 0.5 and self.download > 1024**3

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
