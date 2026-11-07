"""多源元数据身份与快照模型（ADR-025）."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Sequence, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class MediaIdentity(Base):
    """跨 provider 的本地稳定作品身份."""

    __tablename__ = "MEDIA_IDENTITY"
    __table_args__ = (Index("INDX_MEDIA_IDENTITY_TYPE_PROFILE", "MEDIA_TYPE", "CONTENT_PROFILE"),)

    IDENTITY_ID: Mapped[str] = mapped_column(String(26), primary_key=True)
    MEDIA_TYPE: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    MEDIA_KIND: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    CONTENT_PROFILE: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    CANONICAL_TITLE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    YEAR: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ALIASES: Mapped[str | None] = mapped_column(Text, nullable=True)
    PARENT_IDENTITY_ID: Mapped[str | None] = mapped_column(String(26), nullable=True)
    SEASON_NUMBER: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class MediaExternalRef(Base):
    """身份到外部 provider ID 的映射."""

    __tablename__ = "MEDIA_EXTERNAL_REF"
    __table_args__ = (
        UniqueConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", "MEDIA_TYPE", name="UQ_MEDIA_EXTERNAL_REF"),
        Index("INDX_MEDIA_EXTERNAL_REF_IDENTITY", "IDENTITY_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    IDENTITY_ID: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("MEDIA_IDENTITY.IDENTITY_ID", ondelete="CASCADE"),
        nullable=False,
    )
    PROVIDER: Mapped[str] = mapped_column(String(64), nullable=False)
    EXTERNAL_ID: Mapped[str] = mapped_column(String(255), nullable=False)
    MEDIA_TYPE: Mapped[str | None] = mapped_column(String(128), nullable=True)
    SCOPE: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    URL: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    CONFIDENCE: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    LINK_METHOD: Mapped[str] = mapped_column(String(32), nullable=False, default="exact_ref")
    LINK_CONFIDENCE: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    REVIEWED: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IS_PRIMARY: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class MediaMetadataSnapshot(Base):
    """一次合成结果的不可变快照."""

    __tablename__ = "MEDIA_METADATA_SNAPSHOT"
    __table_args__ = (
        Index("INDX_MEDIA_SNAPSHOT_IDENTITY", "IDENTITY_ID"),
        Index("INDX_MEDIA_SNAPSHOT_HASH", "SNAPSHOT_HASH"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    IDENTITY_ID: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("MEDIA_IDENTITY.IDENTITY_ID", ondelete="CASCADE"),
        nullable=False,
    )
    POLICY_KEY: Mapped[str] = mapped_column(String(64), nullable=False)
    CONTENT_PROFILE: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    SCOPE: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    SNAPSHOT_HASH: Mapped[str] = mapped_column(String(64), nullable=False)
    PAYLOAD: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=False)
    PROVIDERS: Mapped[str | None] = mapped_column(Text, nullable=True)
    STATUS: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class MediaFieldOverride(Base):
    """用户/管理员手动锁定的字段值."""

    __tablename__ = "MEDIA_FIELD_OVERRIDE"
    __table_args__ = (
        UniqueConstraint("IDENTITY_ID", "FIELD_NAME", "USER_ID", name="UQ_MEDIA_FIELD_OVERRIDE"),
        Index("INDX_MEDIA_FIELD_OVERRIDE_IDENTITY", "IDENTITY_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    IDENTITY_ID: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("MEDIA_IDENTITY.IDENTITY_ID", ondelete="CASCADE"),
        nullable=False,
    )
    USER_ID: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"),
        nullable=True,
    )
    FIELD_NAME: Mapped[str] = mapped_column(String(128), nullable=False)
    VALUE: Mapped[str] = mapped_column(Text, nullable=False)
    PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    LOCALE: Mapped[str | None] = mapped_column(String(32), nullable=True)
    LOCKED: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# 与项目现有模型命名保持一致
MEDIA_IDENTITY = MediaIdentity
MEDIA_EXTERNAL_REF = MediaExternalRef
MEDIA_METADATA_SNAPSHOT = MediaMetadataSnapshot
MEDIA_FIELD_OVERRIDE = MediaFieldOverride


class PersonIdentity(Base):
    """跨源人员实体（演员/导演/编剧）."""

    __tablename__ = "PERSON_IDENTITY"
    __table_args__ = (Index("INDX_PERSON_IDENTITY_NAME", "CANONICAL_NAME"),)

    PERSON_ID: Mapped[str] = mapped_column(String(26), primary_key=True)
    CANONICAL_NAME: Mapped[str] = mapped_column(String(255), nullable=False)
    ALIASES: Mapped[str | None] = mapped_column(Text, nullable=True)
    IMAGES: Mapped[str | None] = mapped_column(Text, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PersonExternalRef(Base):
    """人员到外部 provider 的映射."""

    __tablename__ = "PERSON_EXTERNAL_REF"
    __table_args__ = (
        UniqueConstraint("PROVIDER", "EXTERNAL_ID", name="UQ_PERSON_EXTERNAL_REF"),
        Index("INDX_PERSON_EXTERNAL_REF_PERSON", "PERSON_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    PERSON_ID: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("PERSON_IDENTITY.PERSON_ID", ondelete="CASCADE"),
        nullable=False,
    )
    PROVIDER: Mapped[str] = mapped_column(String(64), nullable=False)
    EXTERNAL_ID: Mapped[str] = mapped_column(String(255), nullable=False)
    URL: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


PERSON_IDENTITY = PersonIdentity
PERSON_EXTERNAL_REF = PersonExternalRef
