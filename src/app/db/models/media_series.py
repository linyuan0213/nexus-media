"""规范剧集、规范季与来源别名（不依赖 TMDB 的内部剧集模型）."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class MediaSeries(Base):
    """内部规范剧集，来源站点的条目通过别名指向这里."""

    __tablename__ = "MEDIA_SERIES"

    SERIES_KEY: Mapped[str] = mapped_column(String(64), primary_key=True)
    PRIMARY_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PRIMARY_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)
    TITLE: Mapped[str] = mapped_column(String(255), nullable=False)
    ORIGINAL_TITLE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    YEAR: Mapped[str | None] = mapped_column(String(10), nullable=True)
    TOTAL_SEASONS: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    CREATED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)
    UPDATED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)


class MediaSeriesSeason(Base):
    """规范季：同一剧集的 S01/S02...，可记录集号偏移."""

    __tablename__ = "MEDIA_SERIES_SEASON"

    SERIES_KEY: Mapped[str] = mapped_column(String(64), primary_key=True)
    SEASON_NUMBER: Mapped[int] = mapped_column(Integer, primary_key=True)
    TITLE: Mapped[str | None] = mapped_column(String(255), nullable=True)
    YEAR: Mapped[str | None] = mapped_column(String(10), nullable=True)
    TOTAL_EPISODES: Mapped[int | None] = mapped_column(Integer, nullable=True)
    EPISODE_OFFSET: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    PRIMARY_PROVIDER: Mapped[str | None] = mapped_column(String(64), nullable=True)
    PRIMARY_EXTERNAL_ID: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MediaSeriesAlias(Base):
    """来源条目到规范剧集的映射；TMDB 只是可选来源之一."""

    __tablename__ = "MEDIA_SERIES_ALIAS"

    PROVIDER: Mapped[str] = mapped_column(String(64), primary_key=True)
    EXTERNAL_ID: Mapped[str] = mapped_column(String(255), primary_key=True)
    SCOPE: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    SEASON_NUMBER: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    SERIES_KEY: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    CONFIDENCE: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    MAPPING_SOURCE: Mapped[str] = mapped_column(String(32), nullable=False, default="title_rule")
    CREATED_AT: Mapped[str | None] = mapped_column(String(20), nullable=True)
