"""
索引器配置领域实体
映射 INDEXER_CONFIG 表为纯数据结构。
"""

from dataclasses import dataclass

from app.utils.json_utils import JsonUtils


@dataclass
class IndexerConfigEntity:
    """索引器配置领域实体"""

    client_id: str = ""
    enabled: bool = True
    config: dict | None = None

    @classmethod
    def from_orm(cls, orm_obj) -> "IndexerConfigEntity":
        if orm_obj is None:
            return cls()
        config_raw = getattr(orm_obj, "CONFIG", None)
        return cls(
            client_id=getattr(orm_obj, "CLIENT_ID", "") or "",
            enabled=bool(getattr(orm_obj, "ENABLED", 1) or 0),
            config=JsonUtils.loads(config_raw) if config_raw else {},
        )
