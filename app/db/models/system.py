# coding: utf-8
"""
系统字典模型
包含: 系统字典
"""
from sqlalchemy import Column, Index, Integer, Text, String, Sequence

from app.db.models.base import Base


class SYSTEMDICT(Base):
    __tablename__ = 'SYSTEM_DICT'
    __table_args__ = (
        Index('INDX_SYSTEM_DICT', 'TYPE', 'KEY'),
    )

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TYPE = Column(String(255))
    KEY = Column(String(255))
    VALUE = Column(String(255))
    NOTE = Column(Text)
