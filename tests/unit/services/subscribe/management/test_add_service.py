"""订阅重订阅续订点推导测试（修复：转移历史已到 N 集，前端回传旧 current_ep 导致进度卡住）."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.services.subscribe.management.add_service import SubscribeAddService


class _FakeTransferHistory:
    def __init__(self, contiguous):
        self._contiguous = contiguous

    def get_contiguous_transferred_episode_by_ref(self, ref, season=None, media_type=None, start=1):
        return self._contiguous

    def get_contiguous_transferred_episode_by_tmdb(self, tmdbid, season=None, start=1):
        raise AssertionError("不应再按 TMDB 专用接口查询转移历史")


class _FakeDownloadRepo:
    def __init__(self, contiguous):
        self._contiguous = contiguous

    def get_contiguous_completed_episode_by_ref(
        self, *, identity_id, anchor_provider, anchor_external_id, season=None, start=1
    ):
        return self._contiguous

    def get_contiguous_completed_episode_by_tmdb(self, tmdb_id, season=None, start=1):
        raise AssertionError("不应再按 TMDB 专用接口查询下载历史")


class _MediaGatewayAdapter:
    """测试替身：把旧 MediaService mock 映射到网关读接口."""

    def __init__(self, media):
        self.media = media

    def resolve_by_title(self, title, *, media_type=None, cache=True, **kwargs):
        return self.media.get_media_info(
            title=title,
            mtype=media_type,
            strict=kwargs.get("strict"),
            cache=cache,
        )

    def season_summaries(self, tv_info):
        return self.media.get_tmdb_tv_seasons(tv_info=tv_info)

    def resolve_season_episode_count(self, **kwargs):
        provider_data = kwargs.get("provider_data") or {}
        return self.media.get_tmdb_season_episodes_num(tv_info=provider_data, season=kwargs.get("season", 1))

    def lookup(self, *args, **kwargs):
        return self.media.lookup(*args, **kwargs)

    def link_subscription(self, media_info, **kwargs):
        return self.media.link_subscription(media_info, **kwargs)

    def provider_descriptor(self, provider):
        return None

    def provider_is_virtual(self, provider):
        return False


def _build_service(transfer_contiguous=0, download_contiguous=0):
    svc = SubscribeAddService.__new__(SubscribeAddService)
    svc._movie_repo = MagicMock()
    svc._tv_repo = MagicMock()
    svc._media = MagicMock()
    svc._media.get_tmdb_tv_seasons.return_value = [{"season_number": 1, "episode_count": 48}]
    svc._message = MagicMock()
    svc._event_bus = MagicMock()
    svc._system_config = MagicMock()
    svc._web_utils = MagicMock()
    svc._transfer_history_manager = _FakeTransferHistory(transfer_contiguous)
    svc._download_repo = _FakeDownloadRepo(download_contiguous)
    svc._metadata_gateway = cast(Any, _MediaGatewayAdapter(svc._media))
    svc._tv_repo.insert.return_value = 999
    svc._tv_repo.insert_movies.return_value = 999
    return svc


def _make_media_info(tmdb_id=223564):
    mi = MediaInfo()
    mi.tmdb_id = tmdb_id
    mi.type = ProviderMediaType.SERIES
    mi.begin_season = 1
    mi.title = "超超超超超喜欢你的100个女朋友"
    mi.total_episodes = 48
    mi.provider_data = {"id": tmdb_id, "name": mi.title, "season": 1}
    return mi


class TestResubscribeContinuation:
    def test_stale_current_ep_bumped_by_transfer_history(self):
        """转移历史已连续 30 集，前端回传旧 current_ep=26 → 应续订到 31（不重复下载已转移集）."""
        svc = _build_service(transfer_contiguous=30)
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48
        code, msg, media = svc.add_rss_subscribe(
            name="超超超超超喜欢你的100个女朋友",
            year="2023",
            mtype=ProviderMediaType.SERIES,
            season=1,
            total_ep=48,
            current_ep=26,  # 前端回传旧进度
        )
        assert code == 0
        # current_ep 应被历史推导推高到 31（30 集已转移 → 首个待下载 = 31）
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 31
        # lack = 48 - 31 + 1 = 18
        assert inserted_kw["lack"] == 18

    def test_explicit_higher_current_ep_preserved(self):
        """显式指定更高的 current_ep（用户主动从 40 开始）不被历史推导拉低."""
        svc = _build_service(transfer_contiguous=30)
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48
        code, _, _ = svc.add_rss_subscribe(
            name="测试",
            year="2023",
            mtype=ProviderMediaType.SERIES,
            season=1,
            total_ep=48,
            current_ep=40,
        )
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 40
        assert inserted_kw["lack"] == 9  # 48 - 40 + 1

    def test_new_subscription_defaults_current_ep_to_one(self):
        svc = _build_service()
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 12
        code, _, _ = svc.add_rss_subscribe(
            name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, total_ep=12, current_ep=None
        )
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 1
        assert inserted_kw["lack"] == 12

    def test_no_history_uses_current_ep(self):
        """无转移/下载历史时，沿用传入的 current_ep."""
        svc = _build_service(transfer_contiguous=0, download_contiguous=0)
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48
        code, _, _ = svc.add_rss_subscribe(
            name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, total_ep=48, current_ep=5
        )
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 5

    def test_history_bumps_from_download_history(self):
        """下载历史连续集也可作为续订点（转移历史为空时）."""
        svc = _build_service(transfer_contiguous=0, download_contiguous=25)
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48
        code, _, _ = svc.add_rss_subscribe(
            name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, total_ep=48, current_ep=10
        )
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 26


class TestNonTmdbEpisodeCount:
    def test_douban_source_uses_metadata_resolver(self):
        svc = _build_service()
        media = _make_media_info()
        media.provider_data = None  # type: ignore[assignment]
        media.total_episodes = 0
        media.type = ProviderMediaType.ANIME
        media.anchor_provider = "douban"
        media.anchor_external_id = "38396475"
        svc._media.get_media_info.return_value = media
        svc._metadata_gateway = MagicMock()
        svc._metadata_gateway.resolve_by_title.return_value = media
        svc._metadata_gateway.resolve_season_episode_count.return_value = 24

        code, _, _ = svc.add_rss_subscribe(
            name="乱马1/2",
            year="2026",
            mtype=ProviderMediaType.ANIME,
            season=3,
            total_ep=None,
            current_ep=0,
        )

        assert code == 0
        svc._metadata_gateway.resolve_season_episode_count.assert_called_once()
        inserted = svc._tv_repo.insert.call_args.kwargs
        assert inserted["total"] == 24
        assert inserted["total_ep"] == 24
        assert inserted["lack"] == 24


class TestResolvedSeasonContinuation:
    def test_s02_history_does_not_use_s01_progress(self):
        svc = _build_service()
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 12
        svc._series_service = MagicMock()
        svc._series_service.resolve.return_value = SimpleNamespace(
            series_key="series:demo", season_number=2, title="测试剧"
        )
        seen = {}

        class _SeasonAwareHistory:
            def get_contiguous_transferred_episode_by_ref(self, ref, season=None, media_type=None, start=1):
                seen["season"] = season
                return 12 if int(season or 0) == 1 else 0

        class _SeasonAwareDownload:
            def get_contiguous_completed_episode_by_ref(
                self, *, identity_id, anchor_provider, anchor_external_id, season=None, start=1
            ):
                return 0

        svc._transfer_history_manager = _SeasonAwareHistory()
        svc._download_repo = _SeasonAwareDownload()
        # 请求仍按 S01 传入，但剧集解析把标题识别为 S02
        code, _, _ = svc.add_rss_subscribe(
            name="测试剧 第二季", year="2024", mtype=ProviderMediaType.SERIES, season=1, total_ep=12, current_ep=1
        )
        assert code == 0
        assert seen["season"] == 2
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["current_ep"] == 1
        assert inserted_kw["lack"] == 12


class TestDefaultSubscribeSetting:
    """未显式传值的字段应套用默认订阅设置（AI 工具不属于前端表单预填路径）."""

    def test_agent_add_applies_default_over_edition_and_filters(self):
        svc = _build_service()
        svc._system_config.get.return_value = {"over_edition": "1", "restype": "1080p", "pix": "1080p"}
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48

        code, _, _ = svc.add_rss_subscribe(
            name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, channel="auto", state="R"
        )

        assert code == 0
        inserted_kw = svc._tv_repo.insert.call_args.kwargs
        assert inserted_kw["over_edition"] == 1  # 修复前恒为 0（参数默认值是 False 导致判空失效）
        assert inserted_kw["filter_restype"] == "1080p"
        assert inserted_kw["filter_pix"] == "1080p"

    def test_explicit_over_edition_false_wins_over_default(self):
        """显式传入 False 时以调用方为准，不被默认设置覆盖."""
        svc = _build_service()
        svc._system_config.get.return_value = {"over_edition": "1"}
        svc._media.get_media_info.return_value = _make_media_info()
        svc._media.get_tmdb_season_episodes_num.return_value = 48

        svc.add_rss_subscribe(name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, over_edition=False)

        assert svc._tv_repo.insert.call_args.kwargs["over_edition"] == 0


def test_identity_fields_are_passed_to_insert():
    """双写：订阅身份字段应通过 adapter 传入 insert."""
    svc = _build_service()
    svc._media.get_media_info.return_value = _make_media_info()
    svc._media.get_tmdb_season_episodes_num.return_value = 48
    identity_fields = {
        "identity_id": "01J00000000000000000000000",
        "anchor_provider": "tmdb",
        "anchor_external_id": "223564",
        "content_profile": "default",
        "metadata_policy": None,
        "naming_profile": None,
    }
    svc._metadata_gateway = MagicMock()
    svc._metadata_gateway.resolve_by_title.return_value = svc._media.get_media_info.return_value
    svc._metadata_gateway.link_subscription.return_value.as_kwargs.return_value = identity_fields

    code, _, _ = svc.add_rss_subscribe(
        name="测试", year="2023", mtype=ProviderMediaType.SERIES, season=1, total_ep=48, current_ep=1
    )

    assert code == 0
    inserted_kw = svc._tv_repo.insert.call_args.kwargs
    assert inserted_kw["identity_id"] == identity_fields["identity_id"]
    assert inserted_kw["anchor_provider"] == "tmdb"
    assert inserted_kw["anchor_external_id"] == "223564"


def test_douban_only_tv_subscription_without_tmdb():
    """豆瓣条目无 TMDB 匹配时仍可创建订阅，分集数来自豆瓣."""
    svc = _build_service()
    media = MediaInfo()
    media.tmdb_id = "DB:25848328"
    media.douban_id = "25848328"
    media.type = ProviderMediaType.SERIES
    media.title = "最后生还者 第一季"
    media.year = "2023"
    media.begin_season = 1
    media.total_episodes = 9
    cast(Any, media).provider_data = None
    cast(Any, svc)._web_utils.get_mediainfo_from_id.return_value = media
    identity_fields = {
        "identity_id": "01J00000000000000000000001",
        "anchor_provider": "douban",
        "anchor_external_id": "25848328",
        "content_profile": "default",
        "metadata_policy": None,
        "naming_profile": None,
    }
    svc._metadata_gateway = MagicMock()
    svc._metadata_gateway.link_subscription.return_value.as_kwargs.return_value = identity_fields
    svc._tv_repo.insert.return_value = 999

    code, msg, result = svc.add_rss_subscribe(
        name="最后生还者",
        year="2023",
        mtype=ProviderMediaType.SERIES,
        mediaid="DB:25848328",
        season=1,
    )

    assert code == 0
    assert msg in ("", "添加订阅成功")
    inserted_kw = svc._tv_repo.insert.call_args.kwargs
    assert inserted_kw["total"] == 9
    assert inserted_kw["anchor_provider"] == "douban"
    assert inserted_kw["anchor_external_id"] == "25848328"
    svc._media.get_tmdb_season_episodes_num.assert_not_called()


def test_provider_ref_subscribes_demo_movie():
    """演示卡片用 content_id 作锚点、demo_meta ref 取详情，按单片订阅."""
    svc = _build_service()
    svc._metadata_gateway = MagicMock()
    svc._metadata_gateway.lookup.return_value = {
        "title": "START-649",
        "year": "2026",
        "poster": "https://example.com/start-649.jpg",
        "overview": "demo",
        "content_profile": "demo",
    }
    svc._metadata_gateway.link_subscription.return_value.as_kwargs.return_value = {
        "identity_id": "01J00000000000000000000002",
        "anchor_provider": "content_id",
        "anchor_external_id": "START-649",
        "content_profile": "demo",
        "metadata_policy": "provider_only:demo",
        "naming_profile": None,
    }
    svc._movie_repo.insert.return_value = 999

    code, _, _ = svc.add_rss_subscribe(
        name="START-649",
        year="",
        mtype=ProviderMediaType.MOVIE,
        mediaid="content_id:START-649",
        metadata_ref="demo_meta:qAZBWN",
        content_profile="demo",
        metadata_policy="provider_only:demo",
        allow_private=True,
    )

    assert code == 0
    _args, _kwargs = svc._metadata_gateway.lookup.call_args
    assert _args == ("demo_meta", "qAZBWN")
    assert _kwargs["media_type"] == ProviderMediaType.MOVIE
    assert _kwargs["content_profile"] == "demo"
    assert _kwargs["context"].allow_private is True
    inserted_kw = svc._movie_repo.insert.call_args.kwargs
    assert inserted_kw["anchor_provider"] == "content_id"
    assert inserted_kw["anchor_external_id"] == "START-649"
    assert inserted_kw["content_profile"] == "demo"
    assert inserted_kw["media_info"].tmdb_id == ""
    assert inserted_kw["media_info"].anchor_provider == "content_id"
    assert inserted_kw["media_info"].anchor_external_id == "START-649"
    assert inserted_kw["keyword"] == "START-649"
    cast(Any, svc._web_utils.get_mediainfo_from_id).assert_not_called()


def test_provider_ref_subscribes_bangumi_tv():
    """Bangumi provider 的 TV/番剧必须进入电视剧订阅，而不是电影订阅."""
    svc = _build_service()
    svc._metadata_gateway = MagicMock()
    svc._metadata_gateway.lookup.return_value = {
        "title": "测试番剧",
        "year": "2026",
        "media_type": "tv",
        "poster": "https://example.com/anime.jpg",
        "overview": "anime",
        "content_profile": "anime",
    }
    svc._metadata_gateway.link_subscription.return_value.as_kwargs.return_value = {
        "identity_id": "01J00000000000000000000003",
        "anchor_provider": "bangumi",
        "anchor_external_id": "456",
        "content_profile": "anime",
        "metadata_policy": "bangumi_primary",
        "naming_profile": None,
    }
    svc._tv_repo.insert.return_value = 999

    code, _, _ = svc.add_rss_subscribe(
        name="测试番剧",
        year="2026",
        mtype=ProviderMediaType.SERIES,
        season=1,
        total_ep=12,
        mediaid="BG:456",
        metadata_ref="bangumi:456",
        content_profile="anime",
    )

    assert code == 0
    inserted_kw = svc._tv_repo.insert.call_args.kwargs
    assert inserted_kw["anchor_provider"] == "bangumi"
    assert inserted_kw["anchor_external_id"] == "456"
    assert inserted_kw["media_info"].type == ProviderMediaType.ANIME
    svc._movie_repo.insert.assert_not_called()


def test_provider_ref_tmdb_tv_passes_media_type_to_lookup():
    """TMDB 同名数字 ID 可能对应另一部电影，必须带 media_type 查询."""
    svc = _build_service()
    svc._metadata_gateway = MagicMock()
    svc._metadata_gateway.lookup.return_value = {
        "title": "权力的游戏",
        "year": "2011",
        "media_type": "tv",
        "content_profile": "default",
        "seasons": [{"season_number": 1, "episode_count": 10}],
    }
    svc._metadata_gateway.link_subscription.return_value.as_kwargs.return_value = {
        "identity_id": "01J00000000000000000000004",
        "anchor_provider": "tmdb",
        "anchor_external_id": "1399",
        "content_profile": "default",
        "metadata_policy": None,
        "naming_profile": None,
    }
    svc._tv_repo.insert.return_value = 1000

    code, _, _ = svc.add_rss_subscribe(
        name="权力的游戏",
        year="2011",
        mtype=ProviderMediaType.SERIES,
        season=1,
        mediaid="1399",
        metadata_ref="tmdb:1399",
    )

    assert code == 0
    _args, _kwargs = svc._metadata_gateway.lookup.call_args
    assert _args == ("tmdb", "1399")
    assert _kwargs["media_type"] == ProviderMediaType.SERIES
    assert _kwargs["content_profile"] is None
    assert _kwargs["context"].allow_private is False
    inserted = svc._tv_repo.insert.call_args.kwargs
    assert inserted["media_info"].type == ProviderMediaType.SERIES
    assert inserted["total"] == 10
    assert inserted["keyword"] == "权力的游戏"
    svc._movie_repo.insert.assert_not_called()


def test_content_id_anchor_is_normalized_for_subscription_list():
    from app.services.subscribe.management.query_service import _normalized_anchor, _source_label

    assert _normalized_anchor("tmdb", "content_id:JUR-897") == ("content_id", "JUR-897")
    assert _source_label("content_id", "") == "插件"
