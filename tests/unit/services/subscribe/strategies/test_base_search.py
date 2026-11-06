"""BaseSearchStrategy 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.services.subscribe.strategies.base_search import BaseSearchStrategy


class _MediaInfo:
    def __init__(self):
        self.provider_data = {"id": 123}
        self.tmdb_id = 123
        self.title = "Test"
        self.type = "movie"
        self.keyword = None
        self.over_edition = None
        self.res_order = None
        self.begin_season = None
        self.rssid = None

    def set_download_info(self, **kwargs):
        pass

    def set_provider_data(self, info):
        self.provider_data = info

    def get_title_string(self):
        return self.title

    def get_poster_image(self):
        return "http://poster.jpg"


@pytest.fixture
def strategy():
    s = BaseSearchStrategy(
        service=MagicMock(),
        searcher=MagicMock(),
        media_service=MagicMock(),
        media_cache=MagicMock(),
        downloader=MagicMock(),
        filter_service=MagicMock(),
        message=MagicMock(),
    )
    s._ident_cache.clear()
    return s


class TestBaseSearchStrategy:
    def test_set_coordinator(self, strategy):
        coord = MagicMock()
        strategy.set_coordinator(coord)
        assert strategy._coordinator is coord

    def test_search_movies_fuzzy_match(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "fuzzy_match": True}}
        strategy._movie_repo = MagicMock()
        strategy._search_movies()
        strategy._movie_repo.update_state.assert_not_called()

    def test_search_movies_batch_limit(self, strategy):
        subs = {str(i): {"id": i, "name": f"Movie{i}"} for i in range(1, 51)}
        strategy._service.get_subscribe_movies.return_value = subs
        strategy._movie_repo = MagicMock()
        processed = []
        with patch.object(strategy, "_get_media_info", side_effect=lambda *a, **k: processed.append(a) or _MediaInfo()):
            with patch.object(strategy, "_get_batch_limit", return_value=10):
                strategy._search_movies()
        assert len(processed) == 10

    def test_search_movies_tmdb_fail(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        with patch.object(strategy, "_get_media_info", return_value=None):
            strategy._search_movies()
        strategy._movie_repo.update_state.assert_called_with(title=None, year=None, rssid=1, state="E")

    def test_search_movies_already_exists(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        strategy._downloader.check_exists_medias.return_value = (True, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._service.finish_rss_subscribe.assert_called_once()

    def test_search_movies_found(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        result = _MediaInfo()
        result.type = "movie"
        strategy._searcher.search_one_media.return_value = (result, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._service.finish_rss_subscribe.assert_not_called()
        # 下载登记后只标记待转移，等入库事件定稿
        assert any(call.kwargs.get("state") == "C" for call in strategy._movie_repo.update_state.call_args_list)

    def test_search_movies_not_found(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        strategy._searcher.search_one_media.return_value = (None, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        strategy._movie_repo.update_state.assert_called_with(title=None, year=None, rssid=1, state="R")

    def test_search_tvs_tmdb_fail(self, strategy):
        strategy._service.get_subscribe_tvs.return_value = {"1": {"id": 1, "name": "TV"}}
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        with patch.object(strategy, "_get_media_info", return_value=None):
            strategy._search_tvs()
        strategy._tv_repo.update_state.assert_called_with(title=None, year=None, season=None, rssid=1, state="E")

    def test_search_tvs_all_exist(self, strategy):
        strategy._service.get_subscribe_tvs.return_value = {"1": {"id": 1, "name": "TV", "season": 1, "total": 10}}
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        media = _MediaInfo()
        media.type = "tv"
        strategy._downloader.check_exists_medias.return_value = (True, {}, None)
        strategy._tv_episode_repo.get.return_value = None
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_tvs()
        strategy._service.finish_rss_subscribe.assert_called_once()

    def test_search_movies_releases_coordinator_lock(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie"}}
        strategy._movie_repo = MagicMock()
        media = _MediaInfo()
        strategy._searcher.search_one_media.return_value = (None, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        coordinator = MagicMock()
        coordinator.try_acquire.return_value = True
        strategy.set_coordinator(coordinator)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_movies()
        coordinator.try_acquire.assert_called_once()
        coordinator.release.assert_called_once_with(media)

    def test_search_tvs_releases_coordinator_lock(self, strategy):
        strategy._service.get_subscribe_tvs.return_value = {"1": {"id": 1, "name": "TV", "season": 1, "total": 10}}
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        strategy._tv_episode_repo.get.return_value = None
        media = _MediaInfo()
        media.type = "tv"
        strategy._searcher.search_one_media.return_value = (None, {}, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {123: [{"season": 1, "episodes": [1]}]}, None)
        coordinator = MagicMock()
        coordinator.try_acquire.return_value = True
        strategy.set_coordinator(coordinator)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_tvs()
        coordinator.try_acquire.assert_called_once()
        coordinator.release.assert_called_once_with(media)

    def test_get_media_info_with_tmdbid(self, strategy):
        media = _MediaInfo()
        strategy._media_cache.get_tmdb_info.return_value = {"id": 123}
        with patch("app.services.subscribe.strategies.base_search.meta_info") as mock_meta:
            mock_meta.return_value = media
            result = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result is media

    def test_get_media_info_without_tmdbid(self, strategy):
        media = _MediaInfo()
        strategy._media_service.identify.return_value = media
        result = strategy._get_media_info(None, "Name", "2024", MediaType.MOVIE)
        assert result is media
        # 第二次调用应走缓存，identify 只调用一次
        result2 = strategy._get_media_info(None, "Name", "2024", MediaType.MOVIE)
        assert result2 is not media
        assert result2.title == media.title
        strategy._media_service.identify.assert_called_once()

    def test_get_media_info_with_tmdbid_caches(self, strategy):
        media = _MediaInfo()
        strategy._media_cache.get_tmdb_info.return_value = {"id": 123}
        with patch("app.services.subscribe.strategies.base_search.meta_info") as mock_meta:
            mock_meta.return_value = media
            result = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result.tmdb_id == media.tmdb_id
            strategy._media_cache.get_tmdb_info.assert_called_once()
            result2 = strategy._get_media_info(123, "Name", "2024", MediaType.MOVIE)
            assert result2.tmdb_id == media.tmdb_id

    def test_get_media_info_different_keys_not_shared(self, strategy):
        media1 = _MediaInfo()
        media2 = _MediaInfo()
        media2.tmdb_id = 456
        strategy._media_service.identify.side_effect = [media1, media2]
        r1 = strategy._get_media_info(None, "Name1", "2024", MediaType.MOVIE)
        r2 = strategy._get_media_info(None, "Name2", "2024", MediaType.MOVIE)
        assert r1 is media1
        assert r2 is media2
        assert strategy._media_service.identify.call_count == 2

    def test_get_media_info_douban_prefix_does_not_identify_tmdb(self, strategy):
        result = strategy._get_media_info("DB:123", "Name", "2024", MediaType.MOVIE)
        assert result is not None
        assert result.tmdb_id == ""
        assert result.douban_id == "123"
        assert result.anchor_provider == "douban"
        strategy._media_service.identify.assert_not_called()


class TestEffectiveSearchSites:
    def test_uses_subscribe_configured_sites(self, strategy):
        strategy._system_config = MagicMock()
        result = strategy._get_effective_search_sites({"search_sites": ["s1", "s2"]}, MediaType.TV)
        assert result == ["s1", "s2"]
        strategy._system_config.get.assert_not_called()

    def test_fallback_to_default_when_not_configured(self, strategy):
        sys_config = MagicMock()
        sys_config.get.return_value = {"search_sites": ["defaultA"]}
        strategy._system_config = sys_config
        result = strategy._get_effective_search_sites({"search_sites": None}, MediaType.TV)
        assert result == ["defaultA"]

    def test_empty_list_triggers_fallback_not_zero_sites(self, strategy):
        # 空列表会覆盖 effective sites → 应回退默认而非 0 站点搜索
        sys_config = MagicMock()
        sys_config.get.return_value = {"search_sites": ["defaultB"]}
        strategy._system_config = sys_config
        result = strategy._get_effective_search_sites({"search_sites": []}, MediaType.TV)
        assert result == ["defaultB"]

    def test_movie_uses_movie_default_setting(self, strategy):
        sys_config = MagicMock()
        sys_config.get.return_value = {"search_sites": ["movieSite"]}
        strategy._system_config = sys_config
        result = strategy._get_effective_search_sites({"search_sites": None}, MediaType.MOVIE)
        assert result == ["movieSite"]

    def test_no_system_config_returns_none(self, strategy):
        """无默认设置 → None（全部可见站点）"""
        strategy._system_config = None
        assert strategy._get_effective_search_sites({"search_sites": None}, MediaType.TV) is None

    def test_invalid_default_setting_returns_none(self, strategy):
        sys_config = MagicMock()
        sys_config.get.return_value = "not_a_dict"
        strategy._system_config = sys_config
        assert strategy._get_effective_search_sites({"search_sites": None}, MediaType.TV) is None

    def test_empty_default_sites_returns_none(self, strategy):
        """默认设置未配站点 → None（而非零站点）"""
        sys_config = MagicMock()
        sys_config.get.return_value = {"search_sites": []}
        strategy._system_config = sys_config
        assert strategy._get_effective_search_sites({"search_sites": []}, MediaType.TV) is None


class TestSubscribeSearchEnforcesOwnerScope:
    """订阅搜索必须透传归属用户，确保按用户可见站点过滤（防止兜底越权）"""

    def test_search_movies_passes_owner_user_id(self, strategy):
        strategy._system_config = None  # 无默认设置 → sites=None（全部可见）
        strategy._service.get_subscribe_movies.return_value = {"1": {"id": 1, "name": "Movie", "user_id": 7}}
        strategy._movie_repo = MagicMock()
        strategy._searcher.search_one_media.return_value = (None, None, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=_MediaInfo()):
            strategy._search_movies()
        _, kwargs = strategy._searcher.search_one_media.call_args
        assert kwargs["user_id"] == 7
        assert kwargs["sites"] is None

    def test_search_tvs_passes_owner_user_id(self, strategy):
        strategy._system_config = None
        strategy._service.get_subscribe_tvs.return_value = {
            "1": {"id": 1, "name": "TV", "season": 1, "total": 10, "user_id": 8}
        }
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        strategy._tv_episode_repo.get.return_value = None
        media = _MediaInfo()
        media.type = "tv"
        strategy._searcher.search_one_media.return_value = (None, {}, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {123: [{"season": 1, "episodes": [1]}]}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_tvs()
        _, kwargs = strategy._searcher.search_one_media.call_args
        assert kwargs["user_id"] == 8

    def test_search_tvs_applies_anime_type_and_episode_offset(self, strategy):
        """动漫订阅落 ANIME，并把规范季的 EPISODE_OFFSET 传给下载策略."""
        strategy._system_config = None
        strategy._service.get_subscribe_tvs.return_value = {
            "1": {
                "id": 1,
                "name": "Demo Anime",
                "season": "S03",
                "total": 18,
                "user_id": 8,
                "content_profile": "anime",
                "series_key": "series:demo",
                "anchor_provider": "bangumi",
                "anchor_external_id": "1",
            }
        }
        strategy._tv_repo = MagicMock()
        strategy._tv_episode_repo = MagicMock()
        strategy._tv_episode_repo.get.return_value = None
        strategy._series_service.get_episode_offset = MagicMock(return_value=24)
        media = _MediaInfo()
        media.type = "tv"
        strategy._searcher.search_one_media.return_value = (None, {}, None, None)
        strategy._downloader.check_exists_medias.return_value = (False, {}, None)
        with patch.object(strategy, "_get_media_info", return_value=media):
            strategy._search_tvs()

        kwargs = strategy._searcher.search_one_media.call_args.kwargs
        assert media.type == MediaType.ANIME
        entry = kwargs["no_exists"]["series:demo:S03"][0]
        assert entry["episode_offset"] == 24


class TestProviderRefSearch:
    def test_get_media_info_content_id_skips_tmdb(self, strategy):
        media = strategy._get_media_info("content_id:START-660", "タイトル", "2026", MediaType.MOVIE)

        assert media is not None
        assert media.tmdb_id == ""
        assert media.anchor_provider == "content_id"
        assert media.anchor_external_id == "START-660"
        assert not media.provider_data
        strategy._media_service.identify.assert_not_called()

    def test_search_movies_provider_ref_uses_keyword(self, strategy):
        strategy._service.get_subscribe_movies.return_value = {
            "1": {
                "id": 1,
                "name": "タイトル",
                "year": "2026",
                "tmdbid": "content_id:START-660",
                "keyword": "START-660",
            }
        }
        strategy._movie_repo = MagicMock()
        strategy._searcher.search_one_media.return_value = (None, None, None, None)

        strategy._search_movies()

        strategy._searcher.search_one_media.assert_called_once()
        strategy._downloader.check_exists_medias.assert_not_called()
        media = strategy._searcher.search_one_media.call_args.kwargs["media_info"]
        assert media.keyword == "START-660"
        strategy._movie_repo.update_state.assert_called_with(title=None, year=None, rssid=1, state="R")


def test_plugin_anchor_never_queries_tmdb(strategy):
    """DemoMeta 等插件来源只用自己的锚点，不借用 TMDB 识别."""
    strategy._media_cache.get_tmdb_info = MagicMock()

    result = strategy._get_media_info(
        "123",
        "JUR-897",
        "2026",
        MediaType.MOVIE,
        anchor_provider="demo_meta",
        anchor_external_id="JUR-897",
        content_profile="demo",
    )

    assert result is not None
    assert result.anchor_provider == "demo_meta"
    assert result.anchor_external_id == "JUR-897"
    assert result.tmdb_id == ""
    assert not result.provider_data
    strategy._media_cache.get_tmdb_info.assert_not_called()


def test_douban_anchor_can_use_tmdb_supplement(strategy):
    """豆瓣锚点是独立来源，不应补 TMDB."""
    strategy._media_cache.get_tmdb_info = MagicMock(return_value={"id": 123})

    result = strategy._get_media_info(
        123,
        "七龙珠超：比鲁斯",
        "2026",
        MediaType.TV,
        anchor_provider="douban",
        anchor_external_id="38221205",
    )

    assert result is not None
    assert result.anchor_provider == "douban"
    assert result.anchor_external_id == "38221205"
    assert result.tmdb_id == ""
    strategy._media_cache.get_tmdb_info.assert_not_called()


def test_external_movie_anchor_without_provider_data_is_not_error(strategy):
    """插件订阅没有 TMDB 数据也不能被判成错误."""
    strategy._service.get_subscribe_movies.return_value = {
        "1": {
            "id": 1,
            "name": "JUR-897",
            "tmdbid": "",
            "anchor_provider": "demo_meta",
            "anchor_external_id": "JUR-897",
            "content_profile": "demo",
        }
    }
    strategy._movie_repo = MagicMock()
    media = _MediaInfo()
    strategy._searcher.search_one_media.return_value = (None, None, None, None)
    strategy._downloader.check_exists_medias.return_value = (False, {}, None)

    with patch.object(strategy, "_get_media_info", return_value=media):
        strategy._search_movies()

    states = [call.kwargs.get("state") for call in strategy._movie_repo.update_state.call_args_list]
    assert "E" not in states


def test_external_tv_anchor_without_provider_data_is_not_error(strategy):
    """非 TMDB 电视剧没有 provider_data 也不能被判成错误."""
    strategy._service.get_subscribe_tvs.return_value = {
        "1": {
            "id": 1,
            "name": "魔法少女育成计划 restart",
            "season": 1,
            "tmdbid": "",
            "anchor_provider": "bangumi",
            "anchor_external_id": "418229",
            "content_profile": "anime",
        }
    }
    strategy._tv_repo = MagicMock()
    strategy._tv_episode_repo = MagicMock()
    media = _MediaInfo()
    media.type = "tv"
    strategy._searcher.search_one_media.return_value = (None, None, None, None)
    strategy._downloader.check_exists_medias.return_value = (False, {}, None)

    with patch.object(strategy, "_get_media_info", return_value=media):
        strategy._search_tvs()

    states = [call.kwargs.get("state") for call in strategy._tv_repo.update_state.call_args_list]
    assert "E" not in states
