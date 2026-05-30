"""
存储后端仓储
"""

from app.db import auto_commit
from app.db.models import STORAGEBACKEND
from app.db.repositories.base_repository import BaseRepository


class StorageBackendRepository(BaseRepository):
    """存储后端仓储实现"""

    def get_all(self):
        return self._db.query(STORAGEBACKEND).all()

    def get_by_id(self, sid):
        return self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).first()

    def insert(self, name, type, config, enabled=1):
        model = STORAGEBACKEND(NAME=name, TYPE=type, CONFIG=config, ENABLED=int(enabled))
        self._db.insert(model)
        self._db.commit()
        return model.ID

    @auto_commit(BaseRepository._db)
    def update(self, sid, **kwargs):
        self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).update(kwargs)

    @auto_commit(BaseRepository._db)
    def delete(self, sid):
        self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).delete()
