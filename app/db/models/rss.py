"""
RSS相关模型
包含: RSS历史、RSS电影、RSS种子、RSS剧集、RSS剧集分集
"""

from typing import Any

from sqlalchemy import Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class RSSHISTORY(Base):
    __tablename__ = "RSS_HISTORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TYPE: Mapped[str] = mapped_column(String(255))
    RSSID: Mapped[str] = mapped_column(String(255), index=True)
    NAME: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    SEASON: Mapped[str] = mapped_column(String(255))
    IMAGE: Mapped[str] = mapped_column(String(255))
    DESC: Mapped[str] = mapped_column(String(255))
    TOTAL: Mapped[int] = mapped_column(Integer)
    START: Mapped[int] = mapped_column(Integer)
    FINISH_TIME: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSMOVIES(Base):
    __tablename__ = "RSS_MOVIES"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    KEYWORD: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    IMAGE: Mapped[str] = mapped_column(String(255))
    RSS_SITES: Mapped[str] = mapped_column(String(255))
    SEARCH_SITES: Mapped[str] = mapped_column(String(255))
    OVER_EDITION: Mapped[int] = mapped_column(Integer)
    FILTER_ORDER: Mapped[int] = mapped_column(Integer)
    FILTER_RESTYPE: Mapped[str] = mapped_column(String(255))
    FILTER_PIX: Mapped[str] = mapped_column(String(255))
    FILTER_RULE: Mapped[int] = mapped_column(Integer)
    FILTER_TEAM: Mapped[str] = mapped_column(String(255))
    FILTER_INCLUDE: Mapped[str] = mapped_column(Text)
    FILTER_EXCLUDE: Mapped[str] = mapped_column(Text)
    SAVE_PATH: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_SETTING: Mapped[int] = mapped_column(Integer, nullable=True)
    FUZZY_MATCH: Mapped[int] = mapped_column(Integer)
    STATE: Mapped[str] = mapped_column(String(255))
    DESC: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSTORRENTS(Base):
    __tablename__ = "RSS_TORRENTS"
    __table_args__ = (Index("INDX_RSS_TORRENTS_NAME", "TITLE", "YEAR", "SEASON", "EPISODE"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TORRENT_NAME: Mapped[str] = mapped_column(String(255))
    ENCLOSURE: Mapped[str] = mapped_column(String(8192))
    TYPE: Mapped[str] = mapped_column(String(255))
    TITLE: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(10))
    SEASON: Mapped[str] = mapped_column(String(10))
    EPISODE: Mapped[str] = mapped_column(String(10))


class RSSTVS(Base):
    __tablename__ = "RSS_TVS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    KEYWORD: Mapped[str] = mapped_column(String(255))
    SEASON: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    IMAGE: Mapped[str] = mapped_column(String(255))
    RSS_SITES: Mapped[str] = mapped_column(String(255))
    SEARCH_SITES: Mapped[str] = mapped_column(String(255))
    OVER_EDITION: Mapped[int] = mapped_column(Integer)
    FILTER_ORDER: Mapped[int] = mapped_column(Integer)
    FILTER_RESTYPE: Mapped[str] = mapped_column(String(255))
    FILTER_PIX: Mapped[str] = mapped_column(String(255))
    FILTER_RULE: Mapped[int] = mapped_column(Integer)
    FILTER_TEAM: Mapped[str] = mapped_column(String(255))
    FILTER_INCLUDE: Mapped[str] = mapped_column(Text)
    FILTER_EXCLUDE: Mapped[str] = mapped_column(Text)
    SAVE_PATH: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_SETTING: Mapped[int] = mapped_column(Integer, nullable=True)
    FUZZY_MATCH: Mapped[int] = mapped_column(Integer)
    TOTAL_EP: Mapped[int] = mapped_column(Integer)
    CURRENT_EP: Mapped[int] = mapped_column(Integer)
    TOTAL: Mapped[int] = mapped_column(Integer)
    LACK: Mapped[int] = mapped_column(Integer)
    STATE: Mapped[str] = mapped_column(String(255))
    DESC: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RSSTVEPISODES(Base):
    __tablename__ = "RSS_TV_EPISODES"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    RSSID: Mapped[str] = mapped_column(String(255), index=True)
    EPISODES: Mapped[str] = mapped_column(String(255))
