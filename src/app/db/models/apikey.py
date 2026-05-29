"""
API Key 管理模型
包含: API Key 表和使用记录表
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class APIKEY(Base):
    """
    API Key 表
    存储用户生成的 API Key 信息
    """

    __tablename__ = "API_KEYS"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), nullable=False)
    KEY_VALUE: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    KEY_PREFIX: Mapped[str] = mapped_column(String(20), nullable=False)
    STATUS: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    EXPIRES_AT: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    CREATED_BY: Mapped[int] = mapped_column(Integer, nullable=True)
    USE_COUNT: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    LAST_USED_AT: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    DESCRIPTION: Mapped[str] = mapped_column(Text, nullable=True)
    RAW_KEY: Mapped[str] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_API_KEYS_STATUS", "STATUS"),
        Index("ix_API_KEYS_CREATED_AT", "CREATED_AT"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.ID,
            "name": self.NAME,
            "key_value": self.KEY_VALUE,
            "key_prefix": self.KEY_PREFIX,
            "status": self.STATUS,
            "expires_at": self.EXPIRES_AT.isoformat() if self.EXPIRES_AT is not None else None,
            "created_at": self.CREATED_AT.isoformat() if self.CREATED_AT is not None else None,
            "updated_at": self.UPDATED_AT.isoformat() if self.UPDATED_AT is not None else None,
            "created_by": self.CREATED_BY,
            "use_count": self.USE_COUNT,
            "last_used_at": self.LAST_USED_AT.isoformat() if self.LAST_USED_AT is not None else None,
            "description": self.DESCRIPTION,
            "raw_key": self.RAW_KEY,
        }

    def is_expired(self) -> bool:
        if self.EXPIRES_AT is None:
            return False
        return datetime.now() > self.EXPIRES_AT

    def is_active(self) -> bool:
        return bool(self.STATUS is not None and int(self.STATUS) == 1 and not self.is_expired())


class APIKEYLOG(Base):
    """
    API Key 使用记录表
    记录每次 API Key 的使用情况
    """

    __tablename__ = "API_KEY_LOGS"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True)
    API_KEY_ID: Mapped[int] = mapped_column(Integer, nullable=False)
    REQUEST_ID: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    REQUEST_NAME: Mapped[str] = mapped_column(String(255), nullable=True)
    SOURCE_IP: Mapped[str] = mapped_column(String(64), nullable=True)
    USER_AGENT: Mapped[str] = mapped_column(Text, nullable=True)
    REQUEST_PATH: Mapped[str] = mapped_column(String(512), nullable=True)
    REQUEST_METHOD: Mapped[str] = mapped_column(String(10), nullable=True)
    STATUS: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    RESPONSE_CODE: Mapped[int] = mapped_column(Integer, nullable=True)
    ERROR_MESSAGE: Mapped[str] = mapped_column(Text, nullable=True)
    REQUEST_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    RESPONSE_TIME_MS: Mapped[int] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_API_KEY_LOGS_API_KEY_ID", "API_KEY_ID"),
        Index("ix_API_KEY_LOGS_REQUEST_AT", "REQUEST_AT"),
        Index("ix_API_KEY_LOGS_STATUS", "STATUS"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.ID,
            "api_key_id": self.API_KEY_ID,
            "request_id": self.REQUEST_ID,
            "request_name": self.REQUEST_NAME,
            "source_ip": self.SOURCE_IP,
            "user_agent": self.USER_AGENT,
            "request_path": self.REQUEST_PATH,
            "request_method": self.REQUEST_METHOD,
            "status": self.STATUS,
            "response_code": self.RESPONSE_CODE,
            "error_message": self.ERROR_MESSAGE,
            "request_at": self.REQUEST_AT.isoformat() if self.REQUEST_AT is not None else None,
            "response_time_ms": self.RESPONSE_TIME_MS,
        }
