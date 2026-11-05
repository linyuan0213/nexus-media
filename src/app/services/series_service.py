"""规范剧集解析：来源条目 -> 内部 series_key + 规范季号，不依赖 TMDB."""

from dataclasses import dataclass

import log
from app.db.repositories.media_series_repository import MediaSeriesRepository
from app.utils.string_utils import StringUtils


@dataclass
class SeriesResolution:
    series_key: str
    season_number: int
    title: str
    year: str | None
    created: bool = False


class SeriesService:
    def __init__(self, repo: MediaSeriesRepository | None = None):
        self._repo = repo or MediaSeriesRepository()

    @staticmethod
    def split_title_season(title: str) -> tuple[str, int | None]:
        value = str(title or "").strip()
        if not value:
            return "", None
        try:
            parsed = StringUtils.get_keyword_from_string(value)
            base = str(parsed[1] or "").strip() if parsed else ""
            season = parsed[2] if parsed else None
        except Exception:  # noqa: BLE001
            base, season = value, None
        return (base or value), (int(season) if season else None)

    def resolve(
        self,
        *,
        provider: str,
        external_id: str,
        title: str,
        year: str | None = None,
        season_number: int | None = None,
        scope: str = "default",
        total_episodes: int | None = None,
        original_title: str | None = None,
    ) -> SeriesResolution:
        provider = str(provider or "").strip()
        external_id = str(external_id or "").strip()
        if not provider or not external_id:
            base, parsed = self.split_title_season(title)
            return SeriesResolution("", parsed or 1, base, year)

        alias = self._repo.get_alias(provider, external_id, scope)
        if alias is not None:
            series = self._repo.get_series(alias.SERIES_KEY)
            return SeriesResolution(
                series_key=alias.SERIES_KEY,
                season_number=int(alias.SEASON_NUMBER or 1),
                title=series.TITLE if series else title,
                year=series.YEAR if series else year,
            )

        base, parsed_season = self.split_title_season(title)
        season = int(season_number or parsed_season or 1)
        candidates = self._repo.find_series_by_title(base)
        series = None
        if candidates:
            if year:
                same_year = [row for row in candidates if str(row.YEAR or "") == str(year)]
                series = same_year[0] if same_year else candidates[0]
            else:
                series = candidates[0]
        created = False
        if series is None:
            series = self._repo.create_series(
                title=base,
                original_title=original_title,
                year=year,
                provider=provider,
                external_id=external_id,
            )
            created = True

        self._repo.upsert_season(
            series_key=series.SERIES_KEY,
            season_number=season,
            title=str(title or "").strip() or None,
            year=year,
            total_episodes=total_episodes,
            provider=provider,
            external_id=external_id,
        )
        alias_row = self._repo.create_alias(
            provider=provider,
            external_id=external_id,
            scope=scope,
            season_number=season,
            series_key=series.SERIES_KEY,
            confidence=50 if created else 70,
            mapping_source="title_rule",
        )
        if alias_row is None:
            log.warn(f"[Series]别名创建失败，使用新建剧集: {provider}:{external_id}")
        return SeriesResolution(
            series_key=series.SERIES_KEY,
            season_number=season,
            title=series.TITLE,
            year=series.YEAR,
            created=created,
        )

    def list_aliases(self, series_key: str):
        return self._repo.list_aliases(series_key)
