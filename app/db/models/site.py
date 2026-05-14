"""
站点统计相关模型
包含: 站点统计历史、站点用户信息、站点图标、站点做种信息
"""

from sqlalchemy import BigInteger, Column, Float, Index, Integer, Sequence, String, Text, text

from app.db.models.base import Base


class SITESTATISTICSHISTORY(Base):
    __tablename__ = "SITE_STATISTICS_HISTORY"
    __table_args__ = (
        Index("INDX_SITE_STATISTICS_HISTORY_DS", "DATE", "URL"),
        Index("UN_INDX_SITE_STATISTICS_HISTORY_DS", "DATE", "URL", unique=True),
    )

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    SITE = Column(String(255))
    DATE = Column(String(255))
    USER_LEVEL = Column(String(255))
    UPLOAD = Column(BigInteger)
    DOWNLOAD = Column(BigInteger)
    RATIO = Column(Float)
    SEEDING = Column(Integer, server_default=text("0"))
    LEECHING = Column(Integer, server_default=text("0"))
    SEEDING_SIZE = Column(BigInteger, server_default=text("0"))
    BONUS = Column(Float, server_default=text("0.0"))
    URL = Column(String(512))


class SITEUSERINFOSTATS(Base):
    __tablename__ = "SITE_USER_INFO_STATS"
    __table_args__ = (Index("INDX_SITE_USER_INFO_STATS_URL", "URL"),)

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    SITE = Column(String(255), index=True)
    USERNAME = Column(String(255))
    USER_LEVEL = Column(String(255))
    JOIN_AT = Column(String(255))
    UPDATE_AT = Column(String(255))
    UPLOAD = Column(BigInteger)
    DOWNLOAD = Column(BigInteger)
    RATIO = Column(Float)
    SEEDING = Column(Integer)
    LEECHING = Column(Integer)
    SEEDING_SIZE = Column(BigInteger)
    BONUS = Column(Float)
    URL = Column(String(512), unique=True)
    MSG_UNREAD = Column(Integer)
    EXT_INFO = Column(String(255))


class SITEFAVICON(Base):
    __tablename__ = "SITE_FAVICON"

    SITE = Column(String(255), primary_key=True)
    URL = Column(String(512))
    FAVICON = Column(Text)


class SITEUSERSEEDINGINFO(Base):
    __tablename__ = "SITE_USER_SEEDING_INFO"

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    SITE = Column(String(255), index=True)
    # MySQL 不允许 TEXT 类型有默认值，移除 server_default
    SEEDING_INFO = Column(Text)
    UPDATE_AT = Column(String(255))
    URL = Column(String(512), unique=True)
