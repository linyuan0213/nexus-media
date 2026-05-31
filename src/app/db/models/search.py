"""
搜索结果模型
包含: 搜索结果信息
"""

from sqlalchemy import BigInteger, Float, Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SEARCHRESULTINFO(Base):
    __tablename__ = "SEARCH_RESULT_INFO"
    __table_args__ = (
        # 使用前缀索引避免超过 MySQL InnoDB utf8mb4 3072 字节限制
        Index(
            "uq_search_pageurl_site_session",
            "PAGEURL",
            "SITE",
            "SEARCH_SESSION_ID",
            unique=True,
            mysql_length={"PAGEURL": 191},
        ),
    )

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    TORRENT_NAME: Mapped[str] = mapped_column(String(255))
    ENCLOSURE: Mapped[str] = mapped_column(String(8192))
    DESCRIPTION: Mapped[str] = mapped_column(Text)
    TYPE: Mapped[str] = mapped_column(String(255))
    TITLE: Mapped[str] = mapped_column(String(255))
    YEAR: Mapped[str] = mapped_column(String(255))
    SEASON: Mapped[str] = mapped_column(String(255))
    EPISODE: Mapped[str] = mapped_column(String(255))
    ES_STRING: Mapped[str] = mapped_column(String(255))
    VOTE: Mapped[str] = mapped_column(String(255))
    IMAGE: Mapped[str] = mapped_column(String(255))
    POSTER: Mapped[str] = mapped_column(String(255))
    TMDBID: Mapped[str] = mapped_column(String(255))
    OVERVIEW: Mapped[str] = mapped_column(Text)
    RES_TYPE: Mapped[str] = mapped_column(String(255))
    RES_ORDER: Mapped[str] = mapped_column(String(255))
    SIZE: Mapped[int] = mapped_column(BigInteger)
    SEEDERS: Mapped[int] = mapped_column(Integer)
    PEERS: Mapped[int] = mapped_column(Integer)
    SITE: Mapped[str] = mapped_column(String(255))
    SITE_ORDER: Mapped[str] = mapped_column(String(255))
    PAGEURL: Mapped[str] = mapped_column(String(512))
    OTHERINFO: Mapped[str] = mapped_column(Text)
    UPLOAD_VOLUME_FACTOR: Mapped[float] = mapped_column(Float)
    DOWNLOAD_VOLUME_FACTOR: Mapped[float] = mapped_column(Float)
    NOTE: Mapped[str] = mapped_column(Text)
    SEARCH_SESSION_ID: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
