# coding: utf-8
"""
配置相关模型
包含: 过滤器分组、过滤规则、RSS解析器、站点配置、同步路径、用户配置、用户RSS配置
"""
from sqlalchemy import Column, BigInteger, Integer, Text, String, Sequence

from app.db.models.base import Base


class CONFIGFILTERGROUP(Base):
    __tablename__ = 'CONFIG_FILTER_GROUP'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    GROUP_NAME = Column(String(255))
    IS_DEFAULT = Column(String(255))
    NOTE = Column(Text)


class CONFIGFILTERRULES(Base):
    __tablename__ = 'CONFIG_FILTER_RULES'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    # 使用 Integer 类型替代 Text，MySQL 不支持在 TEXT 上创建索引
    GROUP_ID = Column(Integer, index=True)
    ROLE_NAME = Column(String(255))
    PRIORITY = Column(String(255))
    INCLUDE = Column(Text)
    EXCLUDE = Column(Text)
    SIZE_LIMIT = Column(String(255))
    NOTE = Column(Text)


class CONFIGRSSPARSER(Base):
    __tablename__ = 'CONFIG_RSS_PARSER'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    TYPE = Column(String(255))
    FORMAT = Column(String(255))
    PARAMS = Column(Text)
    NOTE = Column(Text)
    SYSDEF = Column(String(255))


class CONFIGSITE(Base):
    __tablename__ = 'CONFIG_SITE'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255))
    PRI = Column(String(255))
    RSSURL = Column(String(512))
    SIGNURL = Column(String(512))
    COOKIE = Column(Text)
    INCLUDE = Column(Text)
    EXCLUDE = Column(Text)
    SIZE = Column(BigInteger)
    NOTE = Column(Text)


class CONFIGSYNCPATHS(Base):
    __tablename__ = 'CONFIG_SYNC_PATHS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    SOURCE = Column(String(255))
    DEST = Column(String(255))
    UNKNOWN = Column(String(255))
    MODE = Column(String(255))
    COMPATIBILITY = Column(Integer)
    RENAME = Column(Integer)
    ENABLED = Column(Integer)
    NOTE = Column(Text)


class CONFIGUSERS(Base):
    __tablename__ = 'CONFIG_USERS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    PASSWORD = Column(String(255))
    PRIS = Column(String(255))


class CONFIGUSERRSS(Base):
    __tablename__ = 'CONFIG_USER_RSS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    ADDRESS = Column(String(255))
    PARSER = Column(String(255))
    INTERVAL = Column(String(255))
    USES = Column(String(255))
    INCLUDE = Column(Text)
    EXCLUDE = Column(Text)
    FILTER = Column(String(255))
    UPDATE_TIME = Column(String(255))
    PROCESS_COUNT = Column(String(255))
    STATE = Column(String(255))
    SAVE_PATH = Column(String(255))
    DOWNLOAD_SETTING = Column(Integer, nullable=True)
    RECOGNIZATION = Column(String(255))
    OVER_EDITION = Column(Integer)
    SITES = Column(String(255))
    FILTER_ARGS = Column(String(255))
    MEDIAINFOS = Column(String(255))
    NOTE = Column(Text)


class MEDIASERVER(Base):
    __tablename__ = 'MEDIASERVER'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255), index=True)
    ENABLED = Column(Integer)
    CONFIG = Column(Text)
    IS_DEFAULT = Column(Integer)
    NOTE = Column(Text)
