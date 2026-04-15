# coding: utf-8
"""
下载相关模型
包含: 下载器配置、下载历史、下载设置
"""
from sqlalchemy import Column, Integer, Text, String, Sequence

from app.db.models.base import Base


class DOWNLOADER(Base):
    __tablename__ = 'DOWNLOADER'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255))
    ENABLED = Column(Integer)
    TYPE = Column(String(255))
    TRANSFER = Column(Integer)
    ONLY_NASTOOL = Column(Integer)
    MATCH_PATH = Column(Integer)
    RMT_MODE = Column(String(255))
    CONFIG = Column(Text)
    DOWNLOAD_DIR = Column(String(255))


class DOWNLOADHISTORY(Base):
    __tablename__ = 'DOWNLOAD_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TITLE = Column(String(255), index=True)
    YEAR = Column(String(255))
    TYPE = Column(String(255))
    TMDBID = Column(String(255))
    SE = Column(String(255))
    VOTE = Column(String(255))
    POSTER = Column(String(255))
    OVERVIEW = Column(Text)
    TORRENT = Column(String(255))
    ENCLOSURE = Column(String(2048), index=True)
    SITE = Column(String(255))
    DESC = Column(String(255))
    DOWNLOADER = Column(String(255))
    DOWNLOAD_ID = Column(String(255), index=True)
    SAVE_PATH = Column(String(512), index=True)
    DATE = Column(String(20), index=True)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class DOWNLOADSETTING(Base):
    __tablename__ = 'DOWNLOAD_SETTING'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255))
    CATEGORY = Column(String(255))
    TAGS = Column(String(255))
    IS_PAUSED = Column(Integer)
    UPLOAD_LIMIT = Column(Integer)
    DOWNLOAD_LIMIT = Column(Integer)
    RATIO_LIMIT = Column(Integer)
    SEEDING_TIME_LIMIT = Column(Integer)
    DOWNLOADER = Column(String(255))
    NOTE = Column(Text)
