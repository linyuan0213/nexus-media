"""
转移相关模型
包含: 转移黑名单、转移历史、未知转移记录
"""

from typing import Any

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TRANSFERBLACKLIST(Base):
    __tablename__ = "TRANSFER_BLACKLIST"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PATH: Mapped[str] = mapped_column(String(512), index=True)


class TRANSFERHISTORY(Base):
    __tablename__ = "TRANSFER_HISTORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    MODE: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(255))
    CATEGORY: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[int] = mapped_column(Integer)
    TITLE: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    SEASON_EPISODE: Mapped[str] = mapped_column(String(255))
    SOURCE: Mapped[str] = mapped_column(String(255))
    SOURCE_PATH: Mapped[str] = mapped_column(String(512), index=True)
    SOURCE_FILENAME: Mapped[str] = mapped_column(String(255), index=True)
    DEST: Mapped[str] = mapped_column(String(255))
    DEST_PATH: Mapped[str] = mapped_column(String(255))
    DEST_FILENAME: Mapped[str] = mapped_column(String(255))
    DST_BACKEND: Mapped[str | None] = mapped_column(String(64), nullable=True)
    DATE: Mapped[str] = mapped_column(String(20), index=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TRANSFERUNKNOWN(Base):
    __tablename__ = "TRANSFER_UNKNOWN"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PATH: Mapped[str] = mapped_column(String(512), index=True)
    DEST: Mapped[str] = mapped_column(String(255))
    MODE: Mapped[str] = mapped_column(String(255))
    STATE: Mapped[str] = mapped_column(String(10), index=True)
