"""
站点统计相关模型
包含: 站点统计历史、站点用户信息、站点图标、站点做种信息
"""

from sqlalchemy import BigInteger, Float, Index, Integer, Sequence, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SITESTATISTICSHISTORY(Base):
    __tablename__ = "SITE_STATISTICS_HISTORY"
    __table_args__ = (
        Index("INDX_SITE_STATISTICS_HISTORY_DS", "DATE", "URL"),
        Index("UN_INDX_SITE_STATISTICS_HISTORY_DS", "DATE", "URL", unique=True),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SITE: Mapped[str] = mapped_column(String(255))
    DATE: Mapped[str] = mapped_column(String(255))
    USER_LEVEL: Mapped[str] = mapped_column(String(255))
    UPLOAD: Mapped[int] = mapped_column(BigInteger)
    DOWNLOAD: Mapped[int] = mapped_column(BigInteger)
    RATIO: Mapped[float] = mapped_column(Float)
    SEEDING: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    LEECHING: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    SEEDING_SIZE: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    BONUS: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    URL: Mapped[str] = mapped_column(String(512))


class SITEUSERINFOSTATS(Base):
    __tablename__ = "SITE_USER_INFO_STATS"
    __table_args__ = (Index("INDX_SITE_USER_INFO_STATS_URL", "URL"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SITE: Mapped[str] = mapped_column(String(255), index=True)
    USERNAME: Mapped[str] = mapped_column(String(255))
    USER_LEVEL: Mapped[str] = mapped_column(String(255))
    JOIN_AT: Mapped[str] = mapped_column(String(255))
    UPDATE_AT: Mapped[str] = mapped_column(String(255))
    UPLOAD: Mapped[int] = mapped_column(BigInteger)
    DOWNLOAD: Mapped[int] = mapped_column(BigInteger)
    RATIO: Mapped[float] = mapped_column(Float)
    SEEDING: Mapped[int] = mapped_column(Integer)
    LEECHING: Mapped[int] = mapped_column(Integer)
    SEEDING_SIZE: Mapped[int] = mapped_column(BigInteger)
    BONUS: Mapped[float] = mapped_column(Float)
    URL: Mapped[str] = mapped_column(String(512), unique=True)
    MSG_UNREAD: Mapped[int] = mapped_column(Integer)
    EXT_INFO: Mapped[str] = mapped_column(String(255))


class SITEFAVICON(Base):
    __tablename__ = "SITE_FAVICON"

    SITE: Mapped[str] = mapped_column(String(255), primary_key=True)
    URL: Mapped[str] = mapped_column(String(512))
    FAVICON: Mapped[str] = mapped_column(Text)


class SITEUSERSEEDINGINFO(Base):
    __tablename__ = "SITE_USER_SEEDING_INFO"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SITE: Mapped[str] = mapped_column(String(255), index=True)
    SEEDING_INFO: Mapped[str] = mapped_column(Text)
    UPDATE_AT: Mapped[str] = mapped_column(String(255))
    URL: Mapped[str] = mapped_column(String(512), unique=True)
