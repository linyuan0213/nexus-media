"""
索引器相关模型
包含: 索引器统计、索引器站点配置、索引器配置
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Sequence, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class INDEXERCONFIG(Base):
    __tablename__ = "INDEXER_CONFIG"
    __table_args__ = (UniqueConstraint("CLIENT_ID", name="UQ_INDEXER_CONFIG_CLIENT_ID"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    CLIENT_ID: Mapped[str] = mapped_column(String(50), nullable=False)
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
    CONFIG: Mapped[str | None] = mapped_column(Text, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


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


class INDEXERSITECONFIG(Base):
    __tablename__ = "INDEXER_SITE_CONFIG"
    __table_args__ = (UniqueConstraint("SITE_NAME", name="UQ_INDEXER_SITE_CONFIG_SITE_NAME"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SITE_NAME: Mapped[str] = mapped_column(String(255), nullable=False)
    SOURCE: Mapped[str] = mapped_column(String(50), nullable=False, default="builtin")
    PUBLIC: Mapped[int] = mapped_column(Integer, default=0)
    DOWNLOAD_SETTING: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
    DEFAULT_SETTINGS: Mapped[str | None] = mapped_column(Text, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
