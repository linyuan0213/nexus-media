"""
IndexerConfig Repository
操作 INDEXER_CONFIG 表，管理各索引器客户端的配置和启用状态。
"""

from datetime import datetime

from sqlalchemy import select

from app.db.models import INDEXERCONFIG
from app.db.repositories.base_repository import BaseRepository
from app.utils.json_utils import JsonUtils


class IndexerConfigRepository(BaseRepository):
    """索引器配置仓储"""

    def get_by_client_id(self, client_id: str) -> dict | None:
        with self.session() as db:
            row = db.execute(select(INDEXERCONFIG).where(INDEXERCONFIG.CLIENT_ID == client_id)).scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    def get_all(self) -> list[dict]:
        with self.session() as db:
            rows = db.execute(select(INDEXERCONFIG)).scalars().all()
        return [self._to_dict(r) for r in rows]

    def upsert(self, client_id: str, enabled: bool | None = None, config: dict | None = None) -> None:
        with self.session() as db:
            existing = db.execute(
                select(INDEXERCONFIG).where(INDEXERCONFIG.CLIENT_ID == client_id)
            ).scalar_one_or_none()

            now = datetime.now()
            if existing:
                if enabled is not None:
                    existing.ENABLED = 1 if enabled else 0
                if config is not None:
                    existing.CONFIG = JsonUtils.dumps(config)
                existing.UPDATED_AT = now
            else:
                row = INDEXERCONFIG(
                    CLIENT_ID=client_id,
                    ENABLED=1 if enabled is None or enabled else 0,
                    CONFIG=JsonUtils.dumps(config) if config else None,
                    CREATED_AT=now,
                    UPDATED_AT=now,
                )
                db.add(row)
            db.commit()

    @staticmethod
    def _to_dict(row: INDEXERCONFIG) -> dict:
        return {
            "client_id": row.CLIENT_ID,
            "enabled": row.ENABLED == 1,
            "config": JsonUtils.loads(row.CONFIG) if row.CONFIG else {},
        }
