"""
媒体同步模型
包含: 媒体同步项目、媒体同步统计
"""

from sqlalchemy import Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import BaseMedia


class MEDIASYNCITEMS(BaseMedia):
    __tablename__ = "MEDIASYNC_ITEMS"
    __table_args__ = (Index("INDX_MEDIASYNC_ITEMS_SL", "SERVER", "LIBRARY"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SERVER: Mapped[str] = mapped_column(String(255))
    LIBRARY: Mapped[str] = mapped_column(String(255))
    ITEM_ID: Mapped[str] = mapped_column(String(255), index=True)
    ITEM_TYPE: Mapped[str] = mapped_column(String(255))
    TITLE: Mapped[str] = mapped_column(String(255), index=True)
    ORGIN_TITLE: Mapped[str] = mapped_column(String(255), index=True)
    YEAR: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(50), index=True)
    IMDBID: Mapped[str] = mapped_column(String(255))
    PATH: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text)
    JSON: Mapped[str] = mapped_column(Text)


class MEDIASYNCSTATISTIC(BaseMedia):
    __tablename__ = "MEDIASYNC_STATISTICS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SERVER: Mapped[str] = mapped_column(String(255), index=True)
    TOTAL_COUNT: Mapped[str] = mapped_column(String(255))
    MOVIE_COUNT: Mapped[str] = mapped_column(String(255))
    TV_COUNT: Mapped[str] = mapped_column(String(255))
    UPDATE_TIME: Mapped[str] = mapped_column(String(255))
