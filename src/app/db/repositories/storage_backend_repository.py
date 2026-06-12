"""
存储后端仓储
"""

from app.db.models import STORAGEBACKEND
from app.db.repositories.base_repository import BaseRepository


class StorageBackendRepository(BaseRepository):
    """存储后端仓储实现"""

    def get_all(self):
        with self.session() as db:
            return db.query(STORAGEBACKEND).all()

    def get_by_id(self, sid):
        with self.session() as db:
            return db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).first()

    def insert(self, name, type, config, enabled=1):
        model = STORAGEBACKEND(NAME=name, TYPE=type, CONFIG=config, ENABLED=int(enabled))
        with self.session() as db:
            db.add(model)
            db.commit()
            return model.ID

    def update(self, sid, **kwargs):
        with self.session() as db:
            db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).update(kwargs)
            db.commit()

    def delete(self, sid):
        with self.session() as db:
            db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).delete()
            db.commit()
