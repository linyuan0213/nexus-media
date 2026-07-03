"""
刷流相关模型
包含: 站点刷流规则、站点刷流任务、站点刷流种子
"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SITEBRUSHRULE(Base):
    __tablename__ = "SITE_BRUSH_RULE"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    TYPE: Mapped[str] = mapped_column(String(10), nullable=False, default="all")
    RSS_RULE: Mapped[str] = mapped_column(Text, nullable=False, default="")
    REMOVE_RULE: Mapped[str] = mapped_column(Text, nullable=False, default="")
    STOP_RULE: Mapped[str] = mapped_column(Text, nullable=False, default="")
    LST_MOD_DATE: Mapped[str] = mapped_column(String(255))


class SITEBRUSHTASK(Base):
    __tablename__ = "SITE_BRUSH_TASK"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    SITE: Mapped[str] = mapped_column(String(255))
    RSSURL: Mapped[str] = mapped_column(String(512))
    FREELEECH: Mapped[str] = mapped_column(String(255))
    RSS_RULE: Mapped[str] = mapped_column(String(255))
    REMOVE_RULE: Mapped[str] = mapped_column(String(255))
    STOP_RULE: Mapped[str] = mapped_column(Text, nullable=False, default="")
    RSS_RULE_ID: Mapped[int | None] = mapped_column(Integer, ForeignKey("SITE_BRUSH_RULE.ID"), nullable=True)
    REMOVE_RULE_ID: Mapped[int | None] = mapped_column(Integer, ForeignKey("SITE_BRUSH_RULE.ID"), nullable=True)
    STOP_RULE_ID: Mapped[int | None] = mapped_column(Integer, ForeignKey("SITE_BRUSH_RULE.ID"), nullable=True)
    SEED_SIZE: Mapped[int] = mapped_column(BigInteger)
    TIME_RANGE: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ACTIVE_WEEKDAYS: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    DOWNLOAD_SWITCH: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    REMOVE_SWITCH: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    STOP_SWITCH: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    DAILY_DELETE_LIMIT: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    MAX_SEEDING: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    HR_LIMIT: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    INTEVAL: Mapped[str] = mapped_column(String(255))
    LABEL: Mapped[str] = mapped_column(String(255))
    SAVEPATH: Mapped[str] = mapped_column(String(255))
    DOWNLOADER: Mapped[str] = mapped_column(String(255))
    TRANSFER: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_COUNT: Mapped[int] = mapped_column(Integer)
    REMOVE_COUNT: Mapped[int] = mapped_column(Integer)
    DOWNLOAD_SIZE: Mapped[int] = mapped_column(BigInteger)
    UPLOAD_SIZE: Mapped[int] = mapped_column(BigInteger)
    SENDMESSAGE: Mapped[str] = mapped_column(String(255))
    STATE: Mapped[str] = mapped_column(String(255))
    LST_MOD_DATE: Mapped[str] = mapped_column(String(255))


class SITEBRUSHTORRENTS(Base):
    __tablename__ = "SITE_BRUSH_TORRENTS"
    __table_args__ = (
        Index("INDX_SITE_BRUSH_TORRENTS_ENCLOSURE", "ENCLOSURE", mysql_length=255),
        Index("INDX_SITE_BRUSH_TORRENTS_TASK_ID", "TASK_ID"),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TASK_ID: Mapped[str] = mapped_column(String(255))
    TORRENT_NAME: Mapped[str] = mapped_column(String(255))
    TORRENT_SIZE: Mapped[str] = mapped_column(Text)
    ENCLOSURE: Mapped[str] = mapped_column(String(8192))
    DOWNLOADER: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_ID: Mapped[str] = mapped_column(String(255), index=True)
    LST_MOD_DATE: Mapped[str] = mapped_column(String(255))

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class BRUSHEVENTLOG(Base):
    __tablename__ = "BRUSH_EVENT_LOG"
    __table_args__ = (Index("INDX_BRUSH_EVENT_LOG_TASK_ID", "TASK_ID"),)

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TASK_ID: Mapped[int] = mapped_column(Integer, nullable=False)
    TASK_NAME: Mapped[str] = mapped_column(String(255), default="")
    TORRENT_NAME: Mapped[str] = mapped_column(String(512), default="")
    DOWNLOAD_ID: Mapped[str] = mapped_column(String(255), default="")
    ACTION: Mapped[str] = mapped_column(String(16), nullable=False)
    REASON: Mapped[str] = mapped_column(String(255), default="")
    DOWNLOADER_NAME: Mapped[str] = mapped_column(String(255), default="")
    SITE_NAME: Mapped[str] = mapped_column(String(255), default="")
    CREATED_AT: Mapped[str] = mapped_column(String(32), default="")

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
