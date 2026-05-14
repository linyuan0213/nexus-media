"""
自定义识别词模型
包含: 自定义识别词、自定义识别词分组
"""
from sqlalchemy import Column, Integer, Sequence, String, Text

from app.db.models.base import Base


class CUSTOMWORDS(Base):
    __tablename__ = 'CUSTOM_WORDS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    REPLACED = Column(String(255))
    REPLACE = Column(String(255))
    FRONT = Column(String(255))
    BACK = Column(String(255))
    OFFSET = Column(String(255))
    TYPE = Column(Integer)
    GROUP_ID = Column(Integer)
    SEASON = Column(Integer)
    ENABLED = Column(Integer)
    REGEX = Column(Integer)
    HELP = Column(String(255))
    NOTE = Column(Text)


class CUSTOMWORDGROUPS(Base):
    __tablename__ = 'CUSTOM_WORD_GROUPS'

    ID = Column(Integer, Sequence('ID'), primary_key=True)
    TITLE = Column(String(255))
    YEAR = Column(String(255))
    TYPE = Column(Integer)
    TMDBID = Column(Integer)
    SEASON_COUNT = Column(Integer)
    NOTE = Column(Text)
