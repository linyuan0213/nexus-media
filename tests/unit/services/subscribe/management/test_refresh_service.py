"""SubscribeRefreshService 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.media.models import MediaInfo
from app.services.subscribe.management.refresh_service import SubscribeRefreshService


class _MediaInfo:
    def __init__(self, tmdb_id, title, year=None, overview=""):
        self.tmdb_id = tmdb_id
        self.title = title
        self.year = year
        self.overview = overview
        self.tmdb_info = {"id": tmdb_id}
        self.release_date = "2024-01-01"
        self.vote_average = 8.5

    def get_message_image(self):
        return f"http://image/{self.tmdb_id}"

    def get_poster_image(self):
        return f"http://poster/{self.tmdb_id}"

    def set_tmdb_info(self, info):
        self.tmdb_info = info


@pytest.fixture
def service():
    return SubscribeRefreshService(
        movie_repo=MagicMock(),
        tv_repo=MagicMock(),
        tv_episode_repo=MagicMock(),
        media_service=MagicMock(),
    )


class TestSubscribeRefreshService:
    def test_refresh_rss_metainfo_movie_update(self, service):
        media = _MediaInfo(123, "Updated Movie", "2024", "overview")
        with patch("app.services.subscribe.management.refresh_service.meta_info") as mock_meta:
            mock_meta.return_value = MediaInfo()
            service._media.get_tmdb_info.return_value = {}
            service._media.get_media_info.return_value = media
            service.refresh_rss_metainfo(
                get_subscribe_movies_fn=lambda state: {"1": {"id": "1", "name": "Old Movie", "year": "2024"}},
                get_subscribe_tvs_fn=lambda state: {},
            )
        service._movie_repo.update_tmdb.assert_called_once()

    def test_refresh_rss_metainfo_movie_skip_with_tmdbid(self, service):
        service.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state: {"1": {"id": "1", "name": "Movie", "tmdbid": "123"}},
            get_subscribe_tvs_fn=lambda state: {},
        )
        service._movie_repo.update_tmdb.assert_not_called()

    def test_refresh_rss_metainfo_movie_fuzzy_match(self, service):
        service.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state: {"1": {"id": "1", "name": "Movie", "fuzzy_match": True}},
            get_subscribe_tvs_fn=lambda state: {},
        )
        service._movie_repo.update_tmdb.assert_not_called()

    def test_refresh_rss_metainfo_tv_update(self, service):
        media = _MediaInfo(456, "Updated TV", "2024", "overview")
        with patch("app.services.subscribe.management.refresh_service.meta_info") as mock_meta:
            mock_meta.return_value = MediaInfo()
            service._media.get_tmdb_info.return_value = {}
            service._media.get_media_info.return_value = media
            service._media.get_tmdb_season_episodes_num.return_value = 10
            with patch("app.services.subscribe.management.refresh_service.transaction_scope"):
                service.refresh_rss_metainfo(
                    get_subscribe_movies_fn=lambda state: {},
                    get_subscribe_tvs_fn=lambda state: {
                        "1": {
                            "id": "1",
                            "name": "Old TV",
                            "year": "2024",
                            "season": 1,
                            "total": 0,
                            "total_ep": 0,
                            "lack": 0,
                        }
                    },
                )
        service._tv_repo.update_tmdb.assert_called_once()
        service._tv_episode_repo.update.assert_called_once()

    def test_refresh_rss_metainfo_tv_skip_with_tmdbid(self, service):
        service.refresh_rss_metainfo(
            get_subscribe_movies_fn=lambda state: {},
            get_subscribe_tvs_fn=lambda state: {"1": {"id": "1", "name": "TV", "tmdbid": "456"}},
        )
        service._tv_repo.update_tmdb.assert_not_called()

    def test_get_media_info_with_tmdbid(self, service):
        with patch("app.services.subscribe.management.refresh_service.meta_info") as mock_meta:
            mi = MagicMock()
            mock_meta.return_value = mi
            service._media.get_tmdb_info.return_value = {"id": 789}
            result = service._SubscribeRefreshService__get_media_info(
                tmdbid=789, name="Direct", year="2024", mtype="movie"
            )
            assert result is mi
            mi.set_tmdb_info.assert_called_once_with({"id": 789})

    def test_refresh_rss_metainfo_cached_reuses_media_info(self, service):
        """refresh_rss_metainfo_cached 对相同 name/year/mtype 只请求一次媒体信息."""
        media = _MediaInfo(123, "Different", "2024", "overview")
        call_count = [0]

        def get_media_info(*args, **kwargs):
            call_count[0] += 1
            return media

        service._media.get_media_info = get_media_info
        with patch("app.services.subscribe.management.refresh_service.meta_info") as mock_meta:
            mock_meta.return_value = MediaInfo()
            service._media.get_tmdb_info.return_value = {}
            service.refresh_rss_metainfo_cached(
                get_subscribe_movies_fn=lambda state: {
                    "1": {"id": "1", "name": "Same Movie", "year": "2024"},
                    "2": {"id": "2", "name": "Same Movie", "year": "2024"},
                },
                get_subscribe_tvs_fn=lambda state: {},
            )
        # 两个电影订阅 name/year 相同，媒体服务应只被调用一次
        assert call_count[0] == 1
        # 同一缓存对象被用于两个订阅，因此更新两次
        assert service._movie_repo.update_tmdb.call_count == 2
