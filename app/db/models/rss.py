"""
RSS相关模型
包含: RSS历史、RSS电影、RSS种子、RSS剧集、RSS剧集分集
"""
from sqlalchemy import Column, Index, Integer, Sequence, String, Text

from app.db.models.base import Base


class RSSHISTORY(Base):
    __tablename__ = 'RSS_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TYPE = Column(String(255))
    RSSID = Column(String(255), index=True)
    NAME = Column(String(255))
    YEAR = Column(String(255))
    TMDBID = Column(String(255))
    SEASON = Column(String(255))
    IMAGE = Column(String(255))
    DESC = Column(String(255))
    TOTAL = Column(Integer)
    START = Column(Integer)
    FINISH_TIME = Column(String(255))
    NOTE = Column(Text)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSMOVIES(Base):
    __tablename__ = 'RSS_MOVIES'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    YEAR = Column(String(255))
    KEYWORD = Column(String(255))
    TMDBID = Column(String(255))
    IMAGE = Column(String(255))
    RSS_SITES = Column(String(255))
    SEARCH_SITES = Column(String(255))
    OVER_EDITION = Column(Integer)
    FILTER_ORDER = Column(Integer)
    FILTER_RESTYPE = Column(String(255))
    FILTER_PIX = Column(String(255))
    FILTER_RULE = Column(Integer)
    FILTER_TEAM = Column(String(255))
    FILTER_INCLUDE = Column(Text)
    FILTER_EXCLUDE = Column(Text)
    SAVE_PATH = Column(String(255))
    DOWNLOAD_SETTING = Column(Integer, nullable=True)
    FUZZY_MATCH = Column(Integer)
    STATE = Column(String(255))
    DESC = Column(String(255))
    NOTE = Column(Text)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSTORRENTS(Base):
    __tablename__ = 'RSS_TORRENTS'
    __table_args__ = (
        Index('INDX_RSS_TORRENTS_NAME', 'TITLE', 'YEAR', 'SEASON', 'EPISODE'),
    )

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TORRENT_NAME = Column(String(255))
    ENCLOSURE = Column(String(8192), index=True)
    TYPE = Column(String(255))
    # 使用 String 替代 Text 以支持 MySQL 索引
    TITLE = Column(String(255))
    YEAR = Column(String(10))
    SEASON = Column(String(10))
    EPISODE = Column(String(10))


class RSSTVS(Base):
    __tablename__ = 'RSS_TVS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    YEAR = Column(String(255))
    KEYWORD = Column(String(255))
    SEASON = Column(String(255))
    TMDBID = Column(String(255))
    IMAGE = Column(String(255))
    RSS_SITES = Column(String(255))
    SEARCH_SITES = Column(String(255))
    OVER_EDITION = Column(Integer)
    FILTER_ORDER = Column(Integer)
    FILTER_RESTYPE = Column(String(255))
    FILTER_PIX = Column(String(255))
    FILTER_RULE = Column(Integer)
    FILTER_TEAM = Column(String(255))
    FILTER_INCLUDE = Column(Text)
    FILTER_EXCLUDE = Column(Text)
    SAVE_PATH = Column(String(255))
    DOWNLOAD_SETTING = Column(Integer, nullable=True)
    FUZZY_MATCH = Column(Integer)
    TOTAL_EP = Column(Integer)
    CURRENT_EP = Column(Integer)
    TOTAL = Column(Integer)
    LACK = Column(Integer)
    STATE = Column(String(255))
    DESC = Column(String(255))
    NOTE = Column(Text)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSTVEPISODES(Base):
    __tablename__ = 'RSS_TV_EPISODES'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    RSSID = Column(String(255), index=True)
    EPISODES = Column(String(255))
