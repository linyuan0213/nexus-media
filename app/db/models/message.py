"""
消息相关模型
包含: 消息客户端配置
"""

from sqlalchemy import Column, Integer, Sequence, String, Text

from app.db.models.base import Base


class MESSAGECLIENT(Base):
    __tablename__ = "MESSAGE_CLIENT"

    ID = Column(Integer, Sequence("ID"), primary_key=True)
    NAME = Column(String(255))
    TYPE = Column(String(255))
    CONFIG = Column(Text)
    SWITCHS = Column(String(255))
    INTERACTIVE = Column(Integer)
    ENABLED = Column(Integer)
    NOTE = Column(Text)
    TEMPLATES = Column(String(255))
