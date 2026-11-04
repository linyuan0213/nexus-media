"""
转移相关模型
包含: 转移黑名单、转移历史、未知转移记录
"""

from typing import Any

from sqlalchemy import Index, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TRANSFERBLACKLIST(Base):
    __tablename__ = "TRANSFER_BLACKLIST"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PATH: Mapped[str] = mapped_column(String(512), index=True)


class TRANSFERHISTORY(Base):
    __tablename__ = "TRANSFER_HISTORY"
    __table_args__ = (
        Index("INDX_TRANSFER_HISTORY_SOURCE", "SOURCE_PATH", "SOURCE_FILENAME"),
        Index("INDX_TRANSFER_HISTORY_TMDBID", "TMDBID"),
        Index("INDX_TRANSFER_HISTORY_DEST", "DEST_PATH", "DEST_FILENAME"),
        Index(
            "uq_transfer_history_source_dest_backend",
            "SOURCE_PATH",
            "SOURCE_FILENAME",
            "DEST_PATH",
            "DEST_FILENAME",
            "DST_BACKEND",
            unique=True,
            mysql_length={
                "SOURCE_PATH": 128,
                "SOURCE_FILENAME": 128,
                "DEST_PATH": 128,
                "DEST_FILENAME": 128,
                "DST_BACKEND": 64,
            },
        ),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    MODE: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(255))
    CATEGORY: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[int] = mapped_column(Integer, index=True)
    TITLE: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    SEASON_EPISODE: Mapped[str] = mapped_column(String(255))
    SOURCE: Mapped[str] = mapped_column(String(255))
    SOURCE_PATH: Mapped[str] = mapped_column(String(512), index=True)
    SOURCE_FILENAME: Mapped[str] = mapped_column(String(255), index=True)
    DEST: Mapped[str] = mapped_column(String(255))
    DEST_PATH: Mapped[str] = mapped_column(String(255))
    DEST_FILENAME: Mapped[str] = mapped_column(String(255))
    POSTER: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    DST_BACKEND: Mapped[str | None] = mapped_column(String(64), nullable=True)
    DATE: Mapped[str] = mapped_column(String(20), index=True)
    IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True, index=True)
    ANCHOR_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ANCHOR_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    SOURCE_STATE: Mapped[str | None] = mapped_column(String(16), nullable=True)
    SOURCE_DELETED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)
    DEST_STATE: Mapped[str | None] = mapped_column(String(16), nullable=True)
    DEST_DELETED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)
    FILES_CHECKED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TRANSFERUNKNOWN(Base):
    __tablename__ = "TRANSFER_UNKNOWN"
    __table_args__ = (Index("INDX_TRANSFER_UNKNOWN_PATH_STATE", "PATH", "STATE"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PATH: Mapped[str] = mapped_column(String(512), index=True)
    DEST: Mapped[str] = mapped_column(String(255))
    MODE: Mapped[str] = mapped_column(String(255))
    STATE: Mapped[str] = mapped_column(String(10), index=True)
