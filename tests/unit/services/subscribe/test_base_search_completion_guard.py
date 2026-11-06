"""搜索策略完成判定回归：无法确认（exist_flag=False 且无缺失信息）时不得判定订阅完成。

回归：base_search 曾用 `library_no_exists` 为空来判“整季已存在”，
而 check_exists_medias 在“集数未知 / 库中无目录 / 无转移历史”时会返回 (False, {}, ...)，
被误当“已完成”，导致只登记下载 1~2 集就删除订阅。
"""

from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.subscribe.strategies.base_search import BaseSearchStrategy
from app.sites.torrent import Torrent


def _build(check_result, monkeypatch):
    monkeypatch.setattr(Torrent, "get_intersection_episodes", staticmethod(lambda target, source, title: target))

    svc = MagicMock()
    rss_info = {
        "id": 41,
        "name": "黑暗召唤师在地下恋爱中",
        "year": "2026",
        "tmdbid": "335790",
        "over_edition": False,
        "keyword": None,
        "season": "S01",
        "total": 12,
        "current_ep": 1,
        "fuzzy_match": False,
        "download_setting": None,
        "save_path": "",
        "user_id": 1,
        "search_sites": [],
        "filter_restype": None,
        "filter_pix": None,
        "filter_team": None,
        "filter_rule": 1002,
        "filter_include": None,
        "filter_exclude": None,
        "filter_free": None,
    }
    svc.get_subscribe_tvs.return_value = {41: rss_info}

    media = MagicMock()
    media.provider_data = {"seasons": []}
    media.tmdb_id = "335790"
    media.type = MediaType.ANIME
    media.total_episodes = 12
    media.get_title_string.return_value = "黑暗召唤师在地下恋爱中 (2026) S01"
    media.get_season_seq.return_value = "1"

    searcher = MagicMock()
    searcher.search_one_media.return_value = (
        None,
        {"335790": [{"season": 1, "episodes": list(range(1, 13)), "total_episodes": 12}]},
        6,
        2,
    )

    media_service = MagicMock()
    media_service.get_tmdb_tv_season_detail.return_value = {}
    media_service.get_tmdb_season_episodes_num.return_value = 0

    downloader = MagicMock()
    downloader.check_exists_medias.return_value = check_result

    tv_ep_repo = MagicMock()
    tv_ep_repo.get.return_value = list(range(1, 13))
    tv_repo = MagicMock()

    strategy = BaseSearchStrategy(
        service=svc,
        searcher=searcher,
        media_service=media_service,
        downloader=downloader,
        filter_service=MagicMock(),
        message=MagicMock(),
        movie_repo=MagicMock(),
        tv_repo=tv_repo,
        tv_episode_repo=tv_ep_repo,
        coordinator=None,
        system_config=None,
    )
    strategy._get_media_info = MagicMock(return_value=media)  # type: ignore[method-assign]
    strategy._get_effective_search_sites = MagicMock(return_value=None)  # type: ignore[method-assign]
    return strategy, svc, tv_repo


def test_unknown_library_state_does_not_finish(monkeypatch):
    strategy, svc, tv_repo = _build((False, {}, None), monkeypatch)

    strategy._search_tvs()

    svc.finish_rss_subscribe.assert_not_called()
    # 应保持运行并记录缺失
    assert svc.update_subscribe_tv_lack.called


def test_confirmed_library_all_present_finishes(monkeypatch):
    strategy, svc, _tv_repo = _build((True, {}, None), monkeypatch)

    strategy._search_tvs()

    svc.finish_rss_subscribe.assert_called_once()
