"""
索引器统计模型
包含: 索引器统计
"""

from typing import Any

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class INDEXERSTATISTICS(Base):
    __tablename__ = "INDEXER_STATISTICS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    INDEXER: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(255))
    SECONDS: Mapped[int] = mapped_column(Integer)
    RESULT: Mapped[str] = mapped_column(String(255))
    DATE: Mapped[str] = mapped_column(String(255))

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
