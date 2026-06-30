"""
索引器站点配置领域实体
映射 ORM 模型 INDEXERSITECONFIG 为纯数据结构。
"""

from dataclasses import dataclass
from datetime import datetime

from app.utils.json_utils import JsonUtils


@dataclass
class IndexerSiteConfigEntity:
    """索引器站点配置领域实体"""

    id: int = 0
    site_name: str = ""
    source: str = "builtin"
    public: bool = False
    download_setting: int | None = None
    enabled: bool = True
    default_settings: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_orm(cls, orm_obj) -> "IndexerSiteConfigEntity":
        """从 ORM 对象转换（兼容 INDEXERSITECONFIG 模型）"""
        if orm_obj is None:
            return cls()
        default_settings_raw = getattr(orm_obj, "DEFAULT_SETTINGS", None)
        return cls(
            id=getattr(orm_obj, "ID", 0) or 0,
            site_name=getattr(orm_obj, "SITE_NAME", "") or "",
            source=getattr(orm_obj, "SOURCE", "builtin") or "builtin",
            public=bool(getattr(orm_obj, "PUBLIC", 0) or 0),
            download_setting=getattr(orm_obj, "DOWNLOAD_SETTING", None),
            enabled=bool(getattr(orm_obj, "ENABLED", 1) or 0),
            default_settings=JsonUtils.loads(default_settings_raw) if default_settings_raw else None,
            created_at=getattr(orm_obj, "CREATED_AT", None),
            updated_at=getattr(orm_obj, "UPDATED_AT", None),
        )
