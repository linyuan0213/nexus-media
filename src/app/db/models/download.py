"""
下载相关模型
包含: 下载器配置、下载历史、下载设置
"""

from typing import Any

from sqlalchemy import Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DOWNLOADER(Base):
    __tablename__ = "DOWNLOADER"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    ENABLED: Mapped[int] = mapped_column(Integer, index=True)
    TYPE: Mapped[str] = mapped_column(String(255), index=True)
    TRANSFER: Mapped[int] = mapped_column(Integer)
    ONLY_NEXUS_MEDIA: Mapped[int] = mapped_column(Integer)
    MATCH_PATH: Mapped[int] = mapped_column(Integer)
    RMT_MODE: Mapped[str] = mapped_column(String(255))
    CONFIG: Mapped[str] = mapped_column(Text)
    DOWNLOAD_DIR: Mapped[str] = mapped_column(Text)


class DOWNLOADHISTORY(Base):
    __tablename__ = "DOWNLOAD_HISTORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TITLE: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    SE: Mapped[str] = mapped_column(String(255))
    VOTE: Mapped[str] = mapped_column(String(255))
    POSTER: Mapped[str] = mapped_column(String(255))
    OVERVIEW: Mapped[str] = mapped_column(Text)
    TORRENT: Mapped[str] = mapped_column(String(255))
    ENCLOSURE: Mapped[str] = mapped_column(String(8192))
    SITE: Mapped[str] = mapped_column(String(255))
    DESC: Mapped[str] = mapped_column(String(255))
    DOWNLOADER: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_ID: Mapped[str] = mapped_column(String(255), index=True)
    SAVE_PATH: Mapped[str] = mapped_column(String(512), index=True)
    STATE: Mapped[str] = mapped_column(String(20), default="downloading")
    DATE: Mapped[str] = mapped_column(String(20), index=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class DOWNLOADSETTING(Base):
    __tablename__ = "DOWNLOAD_SETTING"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    CATEGORY: Mapped[str] = mapped_column(String(255))
    TAGS: Mapped[str] = mapped_column(String(255))
    IS_PAUSED: Mapped[int] = mapped_column(Integer)
    UPLOAD_LIMIT: Mapped[int] = mapped_column(Integer)
    DOWNLOAD_LIMIT: Mapped[int] = mapped_column(Integer)
    RATIO_LIMIT: Mapped[int] = mapped_column(Integer)
    SEEDING_TIME_LIMIT: Mapped[int] = mapped_column(Integer)
    DOWNLOADER: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str | None] = mapped_column(Text, nullable=True)
