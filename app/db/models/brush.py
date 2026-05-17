"""
刷流相关模型
包含: 站点刷流规则、站点刷流任务、站点刷流种子
"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SITEBRUSHRULE(Base):
    __tablename__ = "SITE_BRUSH_RULE"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
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
    RULE_ID: Mapped[int | None] = mapped_column(Integer, ForeignKey("SITE_BRUSH_RULE.ID"), nullable=True)
    SEED_SIZE: Mapped[int] = mapped_column(BigInteger)
    TIME_RANGE: Mapped[str] = mapped_column(Text, nullable=False, default="")
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

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TASK_ID: Mapped[str] = mapped_column(String(255), index=True)
    TORRENT_NAME: Mapped[str] = mapped_column(String(255))
    TORRENT_SIZE: Mapped[str] = mapped_column(Text)
    ENCLOSURE: Mapped[str] = mapped_column(String(8192), index=True)
    DOWNLOADER: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_ID: Mapped[str] = mapped_column(String(255))
    LST_MOD_DATE: Mapped[str] = mapped_column(String(255))

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
