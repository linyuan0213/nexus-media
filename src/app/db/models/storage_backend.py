"""
存储后端模型
包含: 存储后端配置
"""

from sqlalchemy import Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class STORAGEBACKEND(Base):
    __tablename__ = "STORAGE_BACKEND"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(50))
    CONFIG: Mapped[str] = mapped_column(Text)
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
