"""规范剧集、季与来源别名仓储."""

import time
import uuid

from sqlalchemy.exc import IntegrityError

from app.db.models.media_series import MediaSeries, MediaSeriesAlias, MediaSeriesSeason
from app.db.repositories.base_repository import BaseRepository


class MediaSeriesRepository(BaseRepository):
    def get_alias(self, provider: str, external_id: str, scope: str = "default") -> MediaSeriesAlias | None:
        with self.session() as db:
            return (
                db.query(MediaSeriesAlias)
                .filter(
                    MediaSeriesAlias.PROVIDER == provider,
                    MediaSeriesAlias.EXTERNAL_ID == external_id,
                    MediaSeriesAlias.SCOPE == scope,
                )
                .first()
            )

    def get_series(self, series_key: str) -> MediaSeries | None:
        with self.session() as db:
            return db.get(MediaSeries, series_key)

    def find_series_by_title(self, title: str) -> list[MediaSeries]:
        with self.session() as db:
            return db.query(MediaSeries).filter(MediaSeries.TITLE == title).all()

    def list_aliases(self, series_key: str) -> list[MediaSeriesAlias]:
        with self.session() as db:
            return db.query(MediaSeriesAlias).filter(MediaSeriesAlias.SERIES_KEY == series_key).all()

    def create_series(
        self,
        *,
        title: str,
        original_title: str | None,
        year: str | None,
        provider: str,
        external_id: str,
    ) -> MediaSeries:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        row = MediaSeries(
            SERIES_KEY=f"series:{uuid.uuid4().hex}",
            PRIMARY_PROVIDER=provider,
            PRIMARY_EXTERNAL_ID=external_id,
            TITLE=title,
            ORIGINAL_TITLE=original_title,
            YEAR=year,
            TOTAL_SEASONS=0,
            CREATED_AT=now,
            UPDATED_AT=now,
        )
        with self.session() as db:
            db.add(row)
        return row

    def upsert_season(
        self,
        *,
        series_key: str,
        season_number: int,
        title: str | None,
        year: str | None,
        total_episodes: int | None,
        provider: str,
        external_id: str,
    ) -> None:
        with self.session() as db:
            row = db.get(MediaSeriesSeason, (series_key, season_number))
            if row is None:
                db.add(
                    MediaSeriesSeason(
                        SERIES_KEY=series_key,
                        SEASON_NUMBER=season_number,
                        TITLE=title,
                        YEAR=year,
                        TOTAL_EPISODES=total_episodes,
                        EPISODE_OFFSET=0,
                        PRIMARY_PROVIDER=provider,
                        PRIMARY_EXTERNAL_ID=external_id,
                    )
                )
            else:
                row.TITLE = title or row.TITLE
                row.YEAR = year or row.YEAR
                row.TOTAL_EPISODES = total_episodes or row.TOTAL_EPISODES
            series = db.get(MediaSeries, series_key)
            if series is not None and int(series.TOTAL_SEASONS or 0) < season_number:
                series.TOTAL_SEASONS = season_number
                series.UPDATED_AT = time.strftime("%Y-%m-%d %H:%M:%S")

    def create_alias(
        self,
        *,
        provider: str,
        external_id: str,
        scope: str,
        season_number: int,
        series_key: str,
        confidence: int,
        mapping_source: str,
    ) -> MediaSeriesAlias | None:
        row = MediaSeriesAlias(
            PROVIDER=provider,
            EXTERNAL_ID=external_id,
            SCOPE=scope or "default",
            SEASON_NUMBER=season_number,
            SERIES_KEY=series_key,
            CONFIDENCE=confidence,
            MAPPING_SOURCE=mapping_source,
            CREATED_AT=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            with self.session() as db:
                db.add(row)
            return row
        except IntegrityError:
            # 并发创建同一别名：以已有记录为准
            return self.get_alias(provider, external_id, scope)
