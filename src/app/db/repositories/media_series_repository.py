"""规范剧集、季与来源别名仓储."""

import time
import uuid

from sqlalchemy.exc import IntegrityError

from app.db.models import DOWNLOADHISTORY, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.media_series import MediaSeries, MediaSeriesAlias, MediaSeriesSeason
from app.db.models.subscribe import SubscribeHistory, SubscribeTorrents, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository


class MediaSeriesRepository(BaseRepository):
    def get_alias(
        self,
        provider: str,
        external_id: str,
        scope: str = "default",
        season_number: int | None = None,
    ) -> MediaSeriesAlias | None:
        with self.session() as db:
            query = db.query(MediaSeriesAlias).filter(
                MediaSeriesAlias.PROVIDER == provider,
                MediaSeriesAlias.EXTERNAL_ID == external_id,
                MediaSeriesAlias.SCOPE == scope,
            )
            if season_number is not None:
                query = query.filter(MediaSeriesAlias.SEASON_NUMBER == int(season_number))
            return query.order_by(MediaSeriesAlias.SEASON_NUMBER.asc()).first()

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
            return self.get_alias(provider, external_id, scope, season_number)

    def list_series(self, search: str | None = None, limit: int = 200) -> list[MediaSeries]:
        with self.session() as db:
            query = db.query(MediaSeries)
            if search:
                query = query.filter(MediaSeries.TITLE.like(f"%{search}%"))
            return query.order_by(MediaSeries.UPDATED_AT.desc()).limit(limit).all()

    def get_seasons(self, series_key: str) -> list[MediaSeriesSeason]:
        with self.session() as db:
            return (
                db.query(MediaSeriesSeason)
                .filter(MediaSeriesSeason.SERIES_KEY == series_key)
                .order_by(MediaSeriesSeason.SEASON_NUMBER.asc())
                .all()
            )

    def update_season(self, series_key: str, season_number: int, **fields) -> bool:
        with self.session() as db:
            row = db.get(MediaSeriesSeason, (series_key, season_number))
            if row is None:
                return False
            for key, value in fields.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            return True

    def delete_alias(self, provider: str, external_id: str, scope: str, season_number: int | None = None) -> int:
        with self.session() as db:
            query = db.query(MediaSeriesAlias).filter(
                MediaSeriesAlias.PROVIDER == provider,
                MediaSeriesAlias.EXTERNAL_ID == external_id,
                MediaSeriesAlias.SCOPE == scope,
            )
            if season_number is not None:
                query = query.filter(MediaSeriesAlias.SEASON_NUMBER == int(season_number))
            return query.delete(synchronize_session=False)

    def merge_series(self, source_key: str, target_key: str) -> bool:
        if not source_key or not target_key or source_key == target_key:
            return False
        with self.session() as db:
            if db.get(MediaSeries, source_key) is None or db.get(MediaSeries, target_key) is None:
                return False
            db.query(MediaSeriesAlias).filter(MediaSeriesAlias.SERIES_KEY == source_key).update(
                {"SERIES_KEY": target_key}, synchronize_session=False
            )
            existing = {
                row.SEASON_NUMBER
                for row in db.query(MediaSeriesSeason).filter(MediaSeriesSeason.SERIES_KEY == target_key)
            }
            for season in db.query(MediaSeriesSeason).filter(MediaSeriesSeason.SERIES_KEY == source_key):
                if season.SEASON_NUMBER in existing:
                    db.delete(season)
                else:
                    season.SERIES_KEY = target_key
            for model in (
                SubscribeTvs,
                SubscribeHistory,
                SubscribeTorrents,
                DOWNLOADHISTORY,
                TRANSFERHISTORY,
                MediaLifecycle,
                MediaLifecycleEvent,
            ):
                db.query(model).filter(model.SERIES_KEY == source_key).update(
                    {"SERIES_KEY": target_key}, synchronize_session=False
                )
            source = db.get(MediaSeries, source_key)
            if source is not None:
                db.delete(source)
            target = db.get(MediaSeries, target_key)
            if target is not None:
                max_season = max(
                    [
                        int(row.SEASON_NUMBER or 0)
                        for row in db.query(MediaSeriesSeason).filter(MediaSeriesSeason.SERIES_KEY == target_key)
                    ]
                    or [0]
                )
                target.TOTAL_SEASONS = max(int(target.TOTAL_SEASONS or 0), max_season)
            return True
