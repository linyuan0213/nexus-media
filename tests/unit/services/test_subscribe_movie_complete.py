"""电影订阅下载成功后的完成判定 — 登记待转移，入库后再定稿."""

from unittest.mock import MagicMock

from app.domain.entities.rss import SubscribeState
from app.domain.media_types import ProviderMediaType
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy


def _make_strategy():
    service = MagicMock()
    movie_repo = MagicMock()
    strategy = QueueSearchStrategy(
        service=service,
        searcher=MagicMock(),
        media_service=MagicMock(),
        downloader=MagicMock(),
        filter_service=MagicMock(),
        message=MagicMock(),
        rss_repo=MagicMock(),
        movie_repo=movie_repo,
        tv_repo=MagicMock(),
        tv_episode_repo=MagicMock(),
        coordinator=None,
    )
    return strategy, service, movie_repo


def _prepare(strategy, search_result, downloaded_count):
    media = MagicMock()
    media.provider_data = {"id": 123}
    media.type = ProviderMediaType.MOVIE
    media.get_title_string.return_value = "年会不能停2"
    strategy._service.get_subscribe_movies.return_value = {
        1: {
            "id": 1,
            "name": "年会不能停2",
            "year": "2026",
            "tmdbid": "123",
            "over_edition": 0,
            "keyword": "",
            "user_id": 1,
            "download_setting": None,
            "save_path": None,
            "filter_restype": None,
            "filter_pix": None,
            "filter_team": None,
            "filter_rule": None,
            "filter_include": None,
            "filter_exclude": None,
            "filter_free": None,
        }
    }
    strategy._get_media_info = MagicMock(return_value=media)
    strategy._get_effective_search_sites = MagicMock(return_value=["mteam"])
    strategy._downloader.check_exists_medias.return_value = (False, {}, [])
    strategy._searcher.search_one_media.return_value = (search_result, {}, 3, downloaded_count)
    return media


class TestMovieSubscribeCompletion:
    """电影下载成功只登记待转移，不能提前删除订阅."""

    @staticmethod
    def _assert_pending(movie_repo):
        pending = [
            call
            for call in movie_repo.update_state.call_args_list
            if call.kwargs.get("state") == SubscribeState.COMPLETED.value
        ]
        assert pending, "应标记为待转移(COMPLETED)"

    def test_pending_when_downloaded_without_representative_result(self):
        """本轮下载成功但无代表结果（还有其它候选）时也标记待转移"""
        strategy, service, movie_repo = _make_strategy()
        _prepare(strategy, search_result=None, downloaded_count=1)

        strategy._search_movies(state="R")

        service.finish_rss_subscribe.assert_not_called()
        self._assert_pending(movie_repo)

    def test_pending_when_downloaded_with_result(self):
        strategy, service, movie_repo = _make_strategy()
        _prepare(strategy, search_result=MagicMock(), downloaded_count=1)

        strategy._search_movies(state="R")

        service.finish_rss_subscribe.assert_not_called()
        self._assert_pending(movie_repo)

    def test_keeps_running_when_nothing_downloaded(self):
        strategy, service, movie_repo = _make_strategy()
        _prepare(strategy, search_result=None, downloaded_count=0)

        strategy._search_movies(state="R")

        service.finish_rss_subscribe.assert_not_called()
        movie_repo.update_state.assert_called()
