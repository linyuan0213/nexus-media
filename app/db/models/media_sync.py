"""
媒体同步模型
包含: 媒体同步项目、媒体同步统计
"""

from sqlalchemy import Column, Index, Integer, Sequence, String, Text

from app.db.models.base import BaseMedia


class MEDIASYNCITEMS(BaseMedia):
    __tablename__ = "MEDIASYNC_ITEMS"
    __table_args__ = (Index("INDX_MEDIASYNC_ITEMS_SL", "SERVER", "LIBRARY"),)

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    SERVER = Column(String(255))
    LIBRARY = Column(String(255))
    ITEM_ID = Column(String(255), index=True)
    ITEM_TYPE = Column(String(255))
    TITLE = Column(String(255), index=True)
    ORGIN_TITLE = Column(String(255), index=True)
    YEAR = Column(String(255))
    TMDBID = Column(String(50), index=True)
    IMDBID = Column(String(255))
    PATH = Column(String(255))
    NOTE = Column(Text)
    JSON = Column(Text)


class MEDIASYNCSTATISTIC(BaseMedia):
    __tablename__ = "MEDIASYNC_STATISTICS"

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    SERVER = Column(String(255), index=True)
    TOTAL_COUNT = Column(String(255))
    MOVIE_COUNT = Column(String(255))
    TV_COUNT = Column(String(255))
    UPDATE_TIME = Column(String(255))
