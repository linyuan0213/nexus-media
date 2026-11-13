"""媒体生命周期读模型（ADR-026）."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class MediaLifecycle(Base):
    """媒体/单集当前生命周期快照 — 只由 LifecycleProjector 写入."""

    __tablename__ = "MEDIA_LIFECYCLE"
    __table_args__ = (
        UniqueConstraint("IDENTITY_ID", "SEASON", "EPISODE", name="UQ_MEDIA_LIFECYCLE_ITEM"),
        Index("INDX_MEDIA_LIFECYCLE_OWNER", "USER_ID", "STATUS", "LAST_EVENT_AT"),
        Index("INDX_MEDIA_LIFECYCLE_STAGE", "STAGE", "STATUS", "LAST_EVENT_AT"),
        Index("INDX_MEDIA_LIFECYCLE_TRACE", "TRACE_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    IDENTITY_ID: Mapped[str] = mapped_column(String(26), nullable=False)
    SERIES_KEY: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    MEDIA_TYPE: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    SEASON: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    EPISODE: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    TITLE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    YEAR: Mapped[str | None] = mapped_column(String(8), nullable=True)
    POSTER: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    STAGE: Mapped[str] = mapped_column(String(32), nullable=False)
    STATUS: Mapped[str] = mapped_column(String(16), nullable=False)
    RUN_ID: Mapped[str | None] = mapped_column(String(64), nullable=True)
    TRACE_ID: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PROGRESS: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    SOURCE_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    CONTENT_PROFILE: Mapped[str | None] = mapped_column(String(64), nullable=True)
    USER_ID: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    STAGE_STARTED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    LAST_EVENT_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    NEXT_RETRY_AT: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    RETRY_COUNT: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    LAST_ERROR: Mapped[str | None] = mapped_column(Text, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def as_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class MediaLifecycleEvent(Base):
    """生命周期时间线事件 — 只追加，不更新."""

    __tablename__ = "MEDIA_LIFECYCLE_EVENT"
    __table_args__ = (
        UniqueConstraint("EVENT_KEY", name="UQ_MEDIA_LIFECYCLE_EVENT_KEY"),
        Index("INDX_MEDIA_LIFECYCLE_EVENT_ITEM", "IDENTITY_ID", "SEASON", "EPISODE", "OCCURRED_AT"),
        Index("INDX_MEDIA_LIFECYCLE_EVENT_TRACE", "TRACE_ID", "OCCURRED_AT"),
    )

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EVENT_KEY: Mapped[str] = mapped_column(String(128), nullable=False)
    IDENTITY_ID: Mapped[str] = mapped_column(String(26), nullable=False)
    SERIES_KEY: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    MEDIA_TYPE: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    SEASON: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    EPISODE: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    RUN_ID: Mapped[str | None] = mapped_column(String(64), nullable=True)
    TRACE_ID: Mapped[str | None] = mapped_column(String(64), nullable=True)
    STAGE: Mapped[str] = mapped_column(String(32), nullable=False)
    EVENT_TYPE: Mapped[str] = mapped_column(String(64), nullable=False)
    STATUS: Mapped[str] = mapped_column(String(16), nullable=False)
    MESSAGE: Mapped[str | None] = mapped_column(String(512), nullable=True)
    PAYLOAD: Mapped[str | None] = mapped_column(Text, nullable=True)
    USER_ID: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    OCCURRED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    def as_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
