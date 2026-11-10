"""
Agent 记忆模型
包含: 会话（AGENT_CONVERSATION）、消息（AGENT_MESSAGE）
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AGENTCONVERSATION(Base):
    __tablename__ = "AGENT_CONVERSATION"
    __table_args__ = (
        Index(
            "uq_agent_conv_user_channel_session",
            "USER_ID",
            "CHANNEL",
            "SESSION_ID",
            unique=True,
        ),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[str] = mapped_column(String(64), default="", server_default="")
    CHANNEL: Mapped[str] = mapped_column(String(32), default="web", server_default="web")
    SESSION_ID: Mapped[str] = mapped_column(String(128), default="", server_default="")
    TITLE: Mapped[str] = mapped_column(String(120), default="", server_default="")
    SUMMARY: Mapped[str] = mapped_column(Text, default="")
    CHECKPOINT: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    TOKEN_USAGE: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AGENTMESSAGE(Base):
    __tablename__ = "AGENT_MESSAGE"
    __table_args__ = (Index("idx_agent_msg_conversation", "CONVERSATION_ID", "ID"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    CONVERSATION_ID: Mapped[int] = mapped_column(
        Integer, ForeignKey("AGENT_CONVERSATION.ID", ondelete="CASCADE"), index=True
    )
    ROLE: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    CONTENT: Mapped[str] = mapped_column(Text, default="")
    TOOL_CALLS: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    TOKENS: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AGENTTURN(Base):
    __tablename__ = "AGENT_TURN"

    ID: Mapped[str] = mapped_column(String(64), primary_key=True)
    USER_ID: Mapped[str] = mapped_column(String(64), index=True)
    SESSION_ID: Mapped[str] = mapped_column(String(128), index=True)
    STATUS: Mapped[str] = mapped_column(String(32), default="running")
    CANCEL_REQUESTED: Mapped[bool] = mapped_column(Boolean, default=False)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    UPDATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AGENTPENDINGACTION(Base):
    __tablename__ = "AGENT_PENDING_ACTION"

    ID: Mapped[str] = mapped_column(String(64), primary_key=True)
    TURN_ID: Mapped[str] = mapped_column(String(64), ForeignKey("AGENT_TURN.ID", ondelete="CASCADE"), index=True)
    USER_ID: Mapped[str] = mapped_column(String(64), index=True)
    TOOL: Mapped[str] = mapped_column(String(128))
    ARGUMENTS: Mapped[dict] = mapped_column(JSON, default=dict)
    MESSAGE: Mapped[str] = mapped_column(Text, default="")
    STATUS: Mapped[str] = mapped_column(String(32), default="pending")
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    EXPIRES_AT: Mapped[datetime] = mapped_column(DateTime)


class AGENTWEBMESSAGE(Base):
    __tablename__ = "AGENT_WEB_MESSAGE"
    __table_args__ = (
        Index("idx_agent_web_msg_user", "USER_ID", "ID"),
        Index("idx_agent_web_msg_type", "MSG_TYPE", "ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    USER_ID: Mapped[str] = mapped_column(String(64), default="", server_default="")
    KIND: Mapped[str] = mapped_column(String(16), default="notify", server_default="notify")
    MSG_TYPE: Mapped[str] = mapped_column(String(64), default="", server_default="")
    TITLE: Mapped[str] = mapped_column(Text, default="")
    CONTENT: Mapped[str] = mapped_column(Text, default="")
    IMAGE: Mapped[str] = mapped_column(Text, default="")
    URL: Mapped[str] = mapped_column(Text, default="")
    CONTENT_PROFILE: Mapped[str] = mapped_column(String(32), default="", server_default="")
    ITEMS: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    READ: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    READ_AT: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CREATED_AT: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
