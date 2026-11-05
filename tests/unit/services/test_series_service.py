"""规范剧集解析：来源别名 -> 内部 series_key + 规范季号."""

from types import SimpleNamespace
from typing import Any, cast

from app.services.series_service import SeriesService


class _FakeRepo:
    def __init__(self):
        self.series = {}
        self.aliases = {}
        self.seasons = {}

    def get_alias(self, provider, external_id, scope="default"):
        alias = self.aliases.get((provider, external_id, scope))
        if alias is None:
            return None
        return SimpleNamespace(SERIES_KEY=alias["series_key"], SEASON_NUMBER=alias["season"])

    def get_series(self, series_key):
        row = self.series.get(series_key)
        return SimpleNamespace(TITLE=row["title"], YEAR=row["year"]) if row else None

    def find_series_by_title(self, title):
        return [
            SimpleNamespace(SERIES_KEY=key, TITLE=row["title"], YEAR=row["year"])
            for key, row in self.series.items()
            if row["title"] == title
        ]

    def create_series(self, *, title, original_title, year, provider, external_id):
        key = f"series:fake{len(self.series) + 1}"
        self.series[key] = {"title": title, "year": year}
        return SimpleNamespace(SERIES_KEY=key, TITLE=title, YEAR=year)

    def upsert_season(self, **kwargs):
        self.seasons[(kwargs["series_key"], kwargs["season_number"])] = kwargs

    def create_alias(self, **kwargs):
        self.aliases[(kwargs["provider"], kwargs["external_id"], kwargs["scope"])] = {
            "series_key": kwargs["series_key"],
            "season": kwargs["season_number"],
        }
        return SimpleNamespace(SERIES_KEY=kwargs["series_key"])

    def list_aliases(self, series_key):
        return [
            SimpleNamespace(PROVIDER=provider, EXTERNAL_ID=external_id)
            for (provider, external_id, _), value in self.aliases.items()
            if value["series_key"] == series_key
        ]


def _service():
    return SeriesService(repo=cast(Any, _FakeRepo()))


class TestSeriesService:
    def test_same_show_different_entries_share_series(self):
        service = _service()

        first = service.resolve(
            provider="douban",
            external_id="35118256",
            title="赛博朋克：边缘行者 第一季",
            year="2022",
        )
        second = service.resolve(
            provider="douban",
            external_id="37421775",
            title="赛博朋克：边缘行者 第二季",
            year="2026",
        )

        assert first.series_key.startswith("series:")
        assert second.series_key == first.series_key
        assert first.season_number == 1
        assert second.season_number == 2

    def test_alias_is_stable_and_idempotent(self):
        service = _service()
        args: dict[str, Any] = dict(
            provider="bangumi",
            external_id="400602",
            title="赛博朋克：边缘行者 第二季",
            year="2026",
            scope="anime",
        )

        first = service.resolve(**args)
        second = service.resolve(**args)

        assert second.series_key == first.series_key
        assert second.season_number == 2
        aliases = service.list_aliases(first.series_key)
        assert any(alias.PROVIDER == "bangumi" and alias.EXTERNAL_ID == "400602" for alias in aliases)

    def test_title_parser_strips_season_marker(self):
        assert SeriesService.split_title_season("赛博朋克：边缘行者 第二季") == ("赛博朋克：边缘行者", 2)
        assert SeriesService.split_title_season("Cyberpunk Edgerunners Season 2") == (
            "Cyberpunk Edgerunners",
            2,
        )
