# coding: utf-8
"""
转移相关模型
包含: 转移黑名单、转移历史、未知转移记录
"""
from sqlalchemy import Column, Integer, Text, String, Sequence

from app.db.models.base import Base


class TRANSFERBLACKLIST(Base):
    __tablename__ = 'TRANSFER_BLACKLIST'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PATH = Column(String(512), index=True)


class TRANSFERHISTORY(Base):
    __tablename__ = 'TRANSFER_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    MODE = Column(String(255))
    TYPE = Column(String(255))
    CATEGORY = Column(String(255))
    TMDBID = Column(Integer)
    TITLE = Column(String(255), index=True)
    YEAR = Column(String(255))
    SEASON_EPISODE = Column(String(255))
    SOURCE = Column(String(255))
    SOURCE_PATH = Column(String(512), index=True)
    SOURCE_FILENAME = Column(String(255), index=True)
    DEST = Column(String(255))
    DEST_PATH = Column(String(255))
    DEST_FILENAME = Column(String(255))
    DATE = Column(String(20), index=True)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TRANSFERUNKNOWN(Base):
    __tablename__ = 'TRANSFER_UNKNOWN'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PATH = Column(String(512), index=True)
    DEST = Column(String(255))
    MODE = Column(String(255))
    STATE = Column(String(10), index=True)
