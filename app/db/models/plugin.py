# coding: utf-8
"""
插件历史和TMDB黑名单模型
包含: 插件历史、TMDB黑名单、删种任务、自定义RSS任务历史、插件框架v2模型
"""
from datetime import datetime

from sqlalchemy import Column, Integer, Text, String, Sequence, Boolean, DateTime

from app.db.models.base import Base


class PLUGINHISTORY(Base):
    __tablename__ = 'PLUGIN_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PLUGIN_ID = Column(String(255), index=True)
    KEY = Column(String(255), index=True)
    VALUE = Column(String(255))
    DATE = Column(String(255))


class TMDBBLACKLIST(Base):
    __tablename__ = 'TMDB_BLACKLIST'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TMDB_ID = Column(String(50), index=True)
    TITLE = Column(String(255))
    YEAR = Column(String(255))
    MEDIA_TYPE = Column(String(255))
    POSTER_PATH = Column(String(255))
    BACKDROP_PATH = Column(String(255))
    NOTE = Column(Text)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TORRENTREMOVETASK(Base):
    __tablename__ = 'TORRENT_REMOVE_TASK'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    NAME = Column(String(255))
    ACTION = Column(Integer)
    INTERVAL = Column(Integer)
    ENABLED = Column(Integer)
    SAMEDATA = Column(Integer)
    ONLYNASTOOL = Column(Integer)
    DOWNLOADER = Column(String(255))
    CONFIG = Column(Text)
    NOTE = Column(Text)


class USERRSSTASKHISTORY(Base):
    __tablename__ = 'USERRSS_TASK_HISTORY'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TASK_ID = Column(String(255), index=True)
    TITLE = Column(String(255))
    DOWNLOADER = Column(String(255))
    DATE = Column(String(255))


class PLUGINMANIFEST(Base):
    """插件框架v2 - 插件清单表"""
    __tablename__ = 'PLUGIN_MANIFEST'

    ID = Column(String(255), primary_key=True)
    NAME = Column(String(255), nullable=False)
    VERSION = Column(String(255), nullable=False)
    AUTHOR = Column(String(255))
    DESCRIPTION = Column(Text)
    CATEGORY = Column(String(255), default='tool')
    TAGS = Column(Text, default='[]')
    ICON = Column(String(255))
    COLOR = Column(String(255))
    MANIFEST_JSON = Column(Text, nullable=False)
    INSTALLED_AT = Column(DateTime, default=datetime.now)
    UPDATED_AT = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    ENABLED = Column(Boolean, default=False)
    INSTALLED = Column(Boolean, default=True)
    PATH = Column(String(512), nullable=False)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PLUGINCONFIG(Base):
    """插件框架v2 - 插件配置表"""
    __tablename__ = 'PLUGIN_CONFIG'

    PLUGIN_ID = Column(String(255), primary_key=True)
    CONFIG = Column(Text, nullable=False, default='{}')
    UPDATED_AT = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PLUGINLOGS(Base):
    """插件框架v2 - 插件日志表"""
    __tablename__ = 'PLUGIN_LOGS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PLUGIN_ID = Column(String(255), nullable=False, index=True)
    LEVEL = Column(String(50), nullable=False)
    MESSAGE = Column(Text, nullable=False)
    CREATED_AT = Column(DateTime, default=datetime.now)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PLUGINHOOKS(Base):
    """插件框架v2 - 插件Hook订阅表"""
    __tablename__ = 'PLUGIN_HOOKS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    PLUGIN_ID = Column(String(255), nullable=False, index=True)
    EVENT = Column(String(255), nullable=False)
    ENABLED = Column(Boolean, default=True)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
