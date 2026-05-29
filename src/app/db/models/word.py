"""
自定义识别词模型
包含: 自定义识别词、自定义识别词分组
"""

from sqlalchemy import Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CUSTOMWORDS(Base):
    __tablename__ = "CUSTOM_WORDS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    REPLACED: Mapped[str] = mapped_column(String(255))
    REPLACE: Mapped[str] = mapped_column(String(255))
    FRONT: Mapped[str] = mapped_column(String(255))
    BACK: Mapped[str] = mapped_column(String(255))
    OFFSET: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[int] = mapped_column(Integer)
    GROUP_ID: Mapped[int] = mapped_column(Integer)
    SEASON: Mapped[int] = mapped_column(Integer)
    ENABLED: Mapped[int] = mapped_column(Integer)
    REGEX: Mapped[int] = mapped_column(Integer)
    HELP: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)


class CUSTOMWORDGROUPS(Base):
    __tablename__ = "CUSTOM_WORD_GROUPS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TITLE: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[int] = mapped_column(Integer)
    TMDBID: Mapped[int] = mapped_column(Integer)
    SEASON_COUNT: Mapped[int] = mapped_column(Integer)
    NOTE: Mapped[str] = mapped_column(Text)
