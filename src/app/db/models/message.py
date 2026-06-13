"""
消息相关模型
包含: 消息客户端配置
"""

from sqlalchemy import Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class MESSAGECLIENT(Base):
    __tablename__ = "MESSAGE_CLIENT"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(255))
    CONFIG: Mapped[str] = mapped_column(Text)
    SWITCHES: Mapped[str] = mapped_column(String(255))
    INTERACTIVE: Mapped[int] = mapped_column(Integer)
    ENABLED: Mapped[int] = mapped_column(Integer)
    NOTE: Mapped[str] = mapped_column(Text)
    TEMPLATES: Mapped[str] = mapped_column(String(255))
