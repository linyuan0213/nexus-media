# coding: utf-8
"""
刷流相关模型
包含: 站点刷流任务、站点刷流种子
"""
from sqlalchemy import Column, BigInteger, Integer, Text, String, Sequence

from app.db.models.base import Base


class SITEBRUSHTASK(Base):
    __tablename__ = 'SITE_BRUSH_TASK'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    SITE = Column(String(255))
    RSSURL = Column(String(512))
    FREELEECH = Column(String(255))
    RSS_RULE = Column(String(255))
    REMOVE_RULE = Column(String(255))
    STOP_RULE = Column(Text, nullable=False, default="")
    SEED_SIZE = Column(BigInteger)
    TIME_RANGE = Column(Text, nullable=False, default="")
    INTEVAL = Column(String(255))
    LABEL = Column(String(255))
    SAVEPATH = Column(String(255))
    DOWNLOADER = Column(String(255))
    TRANSFER = Column(String(255))
    DOWNLOAD_COUNT = Column(Integer)
    REMOVE_COUNT = Column(Integer)
    DOWNLOAD_SIZE = Column(BigInteger)
    UPLOAD_SIZE = Column(BigInteger)
    SENDMESSAGE = Column(String(255))
    STATE = Column(String(255))
    LST_MOD_DATE = Column(String(255))


class SITEBRUSHTORRENTS(Base):
    __tablename__ = 'SITE_BRUSH_TORRENTS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TASK_ID = Column(String(255), index=True)
    TORRENT_NAME = Column(String(255))
    TORRENT_SIZE = Column(Text)
    ENCLOSURE = Column(String(2048), index=True)
    DOWNLOADER = Column(String(255))
    DOWNLOAD_ID = Column(String(255))
    LST_MOD_DATE = Column(String(255))

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
