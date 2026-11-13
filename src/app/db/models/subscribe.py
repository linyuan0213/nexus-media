"""
RSS相关模型
包含: 订阅历史、订阅电影、订阅种子、订阅剧集、订阅剧集分集
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SubscribeHistory(Base):
    __tablename__ = "SUBSCRIBE_HISTORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"), nullable=True, index=True
    )
    TYPE: Mapped[str] = mapped_column(String(255))
    RSSID: Mapped[str] = mapped_column(String(255), index=True)
    NAME: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    SEASON: Mapped[str] = mapped_column(String(255))
    IMAGE: Mapped[str] = mapped_column(String(255))
    DESC: Mapped[str | None] = mapped_column(Text, nullable=True)
    TOTAL: Mapped[int] = mapped_column(Integer)
    START: Mapped[int] = mapped_column(Integer)
    FINISH_TIME: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    SERIES_KEY: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    METADATA_REF: Mapped[str | None] = mapped_column(String(512), nullable=True)
    METADATA_POLICY: Mapped[str | None] = mapped_column(String(64), nullable=True)
    NAMING_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SubscribeMovies(Base):
    __tablename__ = "SUBSCRIBE_MOVIES"
    __table_args__ = (
        Index(
            "UQ_SUBSCRIBE_MOVIES_USER_ANCHOR",
            "USER_ID",
            "ANCHOR_PROVIDER",
            "ANCHOR_EXTERNAL_ID",
            unique=True,
        ),
        Index("INDX_SUBSCRIBE_MOVIES_IDENTITY", "IDENTITY_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"), nullable=True, index=True
    )
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255), nullable=True)
    KEYWORD: Mapped[str] = mapped_column(String(255), nullable=True)
    TMDBID: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    IMAGE: Mapped[str] = mapped_column(String(255), nullable=True)
    # 站点列表为 JSON 数组，站点多时会超过 varchar(255)
    RSS_SITES: Mapped[str] = mapped_column(Text, nullable=True)
    SEARCH_SITES: Mapped[str] = mapped_column(Text, nullable=True)
    OVER_EDITION: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_ORDER: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_RESTYPE: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_PIX: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_RULE: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_TEAM: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_INCLUDE: Mapped[str] = mapped_column(Text, nullable=True)
    FILTER_EXCLUDE: Mapped[str] = mapped_column(Text, nullable=True)
    FILTER_FREE: Mapped[int] = mapped_column(Integer, nullable=True)
    SAVE_PATH: Mapped[str] = mapped_column(String(255), nullable=True)
    DOWNLOAD_SETTING: Mapped[int] = mapped_column(Integer, nullable=True)
    FUZZY_MATCH: Mapped[int] = mapped_column(Integer, nullable=True)
    STATE: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    STATE_UPDATED_AT: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    RETRY_COUNT: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    NEXT_RETRY_AT: Mapped[str | None] = mapped_column(String(255), nullable=True)
    DESC: Mapped[str | None] = mapped_column(Text, nullable=True)
    NOTE: Mapped[str] = mapped_column(Text, nullable=True)
    ADD_DATE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    METADATA_REF: Mapped[str | None] = mapped_column(String(512), nullable=True)
    METADATA_POLICY: Mapped[str | None] = mapped_column(String(64), nullable=True)
    NAMING_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SubscribeTorrents(Base):
    __tablename__ = "SUBSCRIBE_TORRENTS"
    __table_args__ = (Index("INDX_SUBSCRIBE_TORRENTS_NAME", "TITLE", "YEAR", "SEASON", "EPISODE"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TORRENT_NAME: Mapped[str] = mapped_column(String(255))
    ENCLOSURE: Mapped[str] = mapped_column(String(8192))
    TYPE: Mapped[str] = mapped_column(String(255))
    TITLE: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(10))
    SEASON: Mapped[str] = mapped_column(String(10))
    EPISODE: Mapped[str] = mapped_column(String(10))
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    SERIES_KEY: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SubscribeTvs(Base):
    __tablename__ = "SUBSCRIBE_TVS"
    __table_args__ = (
        Index(
            "UQ_SUBSCRIBE_TVS_USER_ANCHOR_SEASON",
            "USER_ID",
            "ANCHOR_PROVIDER",
            "ANCHOR_EXTERNAL_ID",
            "SEASON",
            unique=True,
        ),
        Index("INDX_SUBSCRIBE_TVS_IDENTITY", "IDENTITY_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"), nullable=True, index=True
    )
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255), nullable=True)
    KEYWORD: Mapped[str] = mapped_column(String(255), nullable=True)
    SEASON: Mapped[str] = mapped_column(String(255), nullable=True)
    TMDBID: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    IMAGE: Mapped[str] = mapped_column(String(255), nullable=True)
    # 站点列表为 JSON 数组，站点多时会超过 varchar(255)
    RSS_SITES: Mapped[str] = mapped_column(Text, nullable=True)
    SEARCH_SITES: Mapped[str] = mapped_column(Text, nullable=True)
    OVER_EDITION: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_ORDER: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_RESTYPE: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_PIX: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_RULE: Mapped[int] = mapped_column(Integer, nullable=True)
    FILTER_TEAM: Mapped[str] = mapped_column(String(255), nullable=True)
    FILTER_INCLUDE: Mapped[str] = mapped_column(Text, nullable=True)
    FILTER_EXCLUDE: Mapped[str] = mapped_column(Text, nullable=True)
    FILTER_FREE: Mapped[int] = mapped_column(Integer, nullable=True)
    SAVE_PATH: Mapped[str] = mapped_column(String(255), nullable=True)
    DOWNLOAD_SETTING: Mapped[int] = mapped_column(Integer, nullable=True)
    FUZZY_MATCH: Mapped[int] = mapped_column(Integer, nullable=True)
    TOTAL_EP: Mapped[int] = mapped_column(Integer, nullable=True)
    CURRENT_EP: Mapped[int] = mapped_column(Integer, nullable=True)
    TOTAL: Mapped[int] = mapped_column(Integer, nullable=True)
    LACK: Mapped[int] = mapped_column(Integer, nullable=True)
    STATE: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    STATE_UPDATED_AT: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    RETRY_COUNT: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    NEXT_RETRY_AT: Mapped[str | None] = mapped_column(String(255), nullable=True)
    DESC: Mapped[str | None] = mapped_column(Text, nullable=True)
    NOTE: Mapped[str] = mapped_column(Text, nullable=True)
    ADD_DATE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    SERIES_KEY: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    METADATA_REF: Mapped[str | None] = mapped_column(String(512), nullable=True)
    METADATA_POLICY: Mapped[str | None] = mapped_column(String(64), nullable=True)
    NAMING_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SubscribeTvEpisodes(Base):
    __tablename__ = "SUBSCRIBE_TV_EPISODES"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"), nullable=True, index=True
    )
    RSSID: Mapped[str] = mapped_column(String(255), index=True)
    # 集号列表（如 1,2,3,...）可能很长，MySQL 下 varchar(255) 会溢出
    EPISODES: Mapped[str] = mapped_column(Text)
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    METADATA_REF: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SubscribeSearchCursor(Base):
    """订阅批量搜索的持久化轮转游标（重启不回到队首）."""

    __tablename__ = "SUBSCRIBE_SEARCH_CURSOR"

    KIND: Mapped[str] = mapped_column(String(32), primary_key=True)
    POSITION: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    UPDATED_AT: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SubscribeCalendarEvent(Base):
    """订阅日历事件读模型；刷新任务写入，接口只读."""

    __tablename__ = "SUBSCRIBE_CALENDAR_EVENTS"
    __table_args__ = (
        Index("UQ_SUBSCRIBE_CALENDAR_EVENT", "USER_ID", "EVENT_KEY", unique=True),
        Index("INDX_SUBSCRIBE_CALENDAR_START", "USER_ID", "START"),
    )

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    USER_ID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"), nullable=True, index=True
    )
    EVENT_KEY: Mapped[str] = mapped_column(String(255), nullable=False)
    START: Mapped[str] = mapped_column(String(10), nullable=False)
    DATA: Mapped[str] = mapped_column(Text, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
