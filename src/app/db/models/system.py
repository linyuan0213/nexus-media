"""
系统字典模型
包含: 系统字典
"""

from sqlalchemy import Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SYSTEMDICT(Base):
    __tablename__ = "SYSTEM_DICT"
    __table_args__ = (Index("INDX_SYSTEM_DICT", "TYPE", "KEY"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TYPE: Mapped[str] = mapped_column(String(255))
    KEY: Mapped[str] = mapped_column(String(255))
    VALUE: Mapped[str] = mapped_column(Text)
    NOTE: Mapped[str] = mapped_column(Text)
