"""TMDB 季匹配：air_date 为 None 时不得下标报错（'NoneType' object is not subscriptable）。"""

from unittest.mock import MagicMock

from app.domain.media_types import ProviderMediaType
from app.media.lookup.tmdb_search import TmdbSearch


def test_season_air_date_none_does_not_log_tmdb_error(monkeypatch):
    client = MagicMock()
    client.search = MagicMock()
    client.search.tv_shows.return_value = [
        {"id": 1, "name": "猛将", "original_name": "猛将", "first_air_date": "2026-01-01"}
    ]
    client.get_blacklist.return_value = []

    ts = TmdbSearch(client)
    info = {
        "media_type": ProviderMediaType.SERIES,
        "name": "猛将",
        "original_name": "猛将",
        "first_air_date": "2026-01-01",
        "seasons": [{"air_date": None, "season_number": 1, "episode_count": 24}],
    }
    monkeypatch.setattr(ts, "_get_detail", lambda *a, **k: info)
    monkeypatch.setattr(ts, "_fetch_allnames", lambda *a, **k: (info, ["猛将", "猛将"]))

    errors: list = []
    monkeypatch.setattr("app.media.lookup.tmdb_search.log.error", lambda *a, **k: errors.append(a))

    ts.search_tv_by_season("猛将", "2026", 1)

    assert not any("连接TMDB出错" in str(a) for a in errors)
