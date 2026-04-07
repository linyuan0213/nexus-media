# coding: utf-8
"""
索引器统计模型
包含: 索引器统计
"""
from sqlalchemy import Column, Integer, String, Sequence

from app.db.models.base import Base


class INDEXERSTATISTICS(Base):
    __tablename__ = 'INDEXER_STATISTICS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    INDEXER = Column(String(255))
    TYPE = Column(String(255))
    SECONDS = Column(Integer)
    RESULT = Column(String(255))
    DATE = Column(String(255))

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
