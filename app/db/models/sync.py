"""
同步历史模型
包含: 同步历史
"""

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SYNCHISTORY(Base):
    __tablename__ = "SYNC_HISTORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PATH: Mapped[str] = mapped_column(String(512), index=True)
    SRC: Mapped[str] = mapped_column(String(255))
    DEST: Mapped[str] = mapped_column(String(255))
