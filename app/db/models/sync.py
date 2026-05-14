"""
同步历史模型
包含: 同步历史
"""
from sqlalchemy import Column, Integer, Sequence, String

from app.db.models.base import Base


class SYNCHISTORY(Base):
    __tablename__ = 'SYNC_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PATH = Column(String(512), index=True)
    SRC = Column(String(255))
    DEST = Column(String(255))
