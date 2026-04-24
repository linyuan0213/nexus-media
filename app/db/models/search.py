# coding: utf-8
"""
搜索结果模型
包含: 搜索结果信息
"""
from sqlalchemy import Column, Float, Integer, BigInteger, Text, String, Sequence

from app.db.models.base import Base


class SEARCHRESULTINFO(Base):
    __tablename__ = 'SEARCH_RESULT_INFO'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TORRENT_NAME = Column(String(255))
    ENCLOSURE = Column(String(8192))
    DESCRIPTION = Column(Text)
    TYPE = Column(String(255))
    TITLE = Column(String(255))
    YEAR = Column(String(255))
    SEASON = Column(String(255))
    EPISODE = Column(String(255))
    ES_STRING = Column(String(255))
    VOTE = Column(String(255))
    IMAGE = Column(String(255))
    POSTER = Column(String(255))
    TMDBID = Column(String(255))
    OVERVIEW = Column(Text)
    RES_TYPE = Column(String(255))
    RES_ORDER = Column(String(255))
    SIZE = Column(BigInteger)
    SEEDERS = Column(Integer)
    PEERS = Column(Integer)
    SITE = Column(String(255))
    SITE_ORDER = Column(String(255))
    PAGEURL = Column(String(512))
    OTHERINFO = Column(Text)
    UPLOAD_VOLUME_FACTOR = Column(Float)
    DOWNLOAD_VOLUME_FACTOR = Column(Float)
    NOTE = Column(Text)
