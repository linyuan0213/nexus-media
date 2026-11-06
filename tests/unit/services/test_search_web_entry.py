"""Web 搜索统一入口（make_web_search_fn）单元测试"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.infrastructure.external.tmdbv3api.as_obj import AsObj
from app.media.models import MediaInfo
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_web_entry import make_web_search_fn


class TestMakeWebSearchFn:
    def test_success_when_results(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 5, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, msg = fn("流浪地球")
        assert code == 0
        assert msg == ""
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.keyword == "流浪地球"
        assert ctx.persist is True

    def test_no_results(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 0, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, msg = fn("不存在的资源")
        assert code == 1
        assert "未搜索到" in msg

    def test_anchor_resolves_media(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 3, 0)
        fake_media = MagicMock()
        orchestrator.resolve_anchor_media.return_value = fake_media
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, _ = fn(
            "x",
            anchor_provider="douban",
            anchor_external_id="36139980",
            media_type=MediaType.TV,
        )
        assert code == 0
        orchestrator.resolve_anchor_media.assert_called_once()
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.match_media is fake_media

    def test_anchor_unresolved_returns_error(self):
        orchestrator = MagicMock()
        orchestrator.resolve_anchor_media.return_value = None
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, msg = fn("x", anchor_provider="douban", anchor_external_id="99999")
        assert code == -1
        orchestrator.orchestrate.assert_not_called()
        orchestrator.begin_search.assert_called_once()
        orchestrator.end_search.assert_called_once()

    def test_progress_starts_before_anchor_resolution(self):
        """SSE 依赖进度记录；锚点解析前必须已建立 search:{session} 进度."""
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 3, 0)

        def resolve(*args, **kwargs):
            assert orchestrator.begin_search.called
            return MagicMock()

        orchestrator.resolve_anchor_media.side_effect = resolve
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, _ = fn(
            "x",
            session_id="sid-1",
            anchor_provider="douban",
            anchor_external_id="36139980",
        )
        assert code == 0
        orchestrator.begin_search.assert_called_once_with("sid-1", "x")
        orchestrator.end_search.assert_called_once_with("sid-1")

    def test_slow_anchor_resolution_falls_back_without_blocking(self, monkeypatch):
        """元数据源卡住时按超时回退关键词，搜索不能一直停在 0%."""
        monkeypatch.setattr("app.services.search_web_entry.ANCHOR_RESOLVE_TIMEOUT", 0.05)
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 2, 0)

        def slow(*args, **kwargs):
            time.sleep(0.5)
            return None

        orchestrator.resolve_content_id_media.side_effect = slow
        fn = make_web_search_fn(orchestrator, system_config=None)
        started = time.monotonic()
        code, msg = fn(
            "DEMO-4025269",
            anchor_provider="content_id",
            anchor_external_id="DEMO-4025269",
            content_profile="demo",
            media_type=MediaType.MOVIE,
        )
        elapsed = time.monotonic() - started
        assert code == 0
        assert msg == ""
        assert elapsed < 0.4
        orchestrator.orchestrate.assert_called_once()
        orchestrator.end_search.assert_called_once()

    def test_content_id_anchor_unresolved_falls_back_to_keyword(self):
        orchestrator = MagicMock()
        orchestrator.resolve_content_id_media.return_value = None
        orchestrator.orchestrate.return_value = (None, {}, 2, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)
        code, msg = fn(
            "DEMO-4025269",
            anchor_provider="content_id",
            anchor_external_id="DEMO-4025269",
            content_profile="demo",
            media_type=MediaType.MOVIE,
        )
        assert code == 0
        assert msg == ""
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.match_media is not None
        assert ctx.match_media.content_profile == "demo"
        assert ctx.match_media.anchor_provider == "content_id"
        assert ctx.match_media.anchor_external_id == "DEMO-4025269"

    def test_movie_search_sets_result_type_filter(self):
        """电影资源搜索必须带 type=MOVIE，供结果过滤器排除剧集."""
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)

        fn("生化危机：爆发夜", media_type=MediaType.MOVIE)

        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["type"] == MediaType.MOVIE

    def test_requested_movie_type_overrides_anchor_default_tv(self):
        orchestrator = MagicMock()
        resolved = MediaInfo(title="生化危机：爆发夜", type=MediaType.TV)
        resolved.year = "2026"
        orchestrator.resolve_anchor_media.return_value = resolved
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)

        fn(
            "生化危机：爆发夜",
            anchor_provider="douban",
            anchor_external_id="37068446",
            media_type=MediaType.MOVIE,
        )

        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.match_media.type == MediaType.MOVIE
        assert ctx.filter_args["type"] == MediaType.MOVIE

    def test_content_id_fallback_keeps_selected_provider(self):
        """编号详情失败时不能用内部 content_id 作为来源展示."""
        orchestrator = MagicMock()
        orchestrator.resolve_content_id_media.return_value = None
        orchestrator.orchestrate.return_value = (None, {}, 0, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)
        fn(
            "DEMO-522 演示内容",
            anchor_provider="content_id",
            anchor_external_id="DEMO-522",
            content_profile="demo",
            media_type=MediaType.MOVIE,
            filters={"metadata_source": "demo_source", "content_profile": "demo"},
        )
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.match_media is not None
        assert ctx.match_media.provider == "demo_source"
        assert ctx.match_media.metadata_ref == "demo_source:DEMO-522"
        assert ctx.match_media.anchor_provider == "content_id"

    def test_anime_uses_tv_candidate_type_but_keeps_anime_display_type(self):
        """动漫资源按电视形态过滤，但入库类型仍是动漫，二者不能互相覆盖."""
        orchestrator = MagicMock()
        resolved = MediaInfo(title="演示番剧", type=MediaType.TV)
        orchestrator.resolve_anchor_media.return_value = resolved
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)

        fn(
            "演示番剧",
            anchor_provider="tmdb",
            anchor_external_id="1001",
            content_profile="anime",
            media_type=MediaType.ANIME,
        )

        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["type"] == MediaType.TV
        assert ctx.match_media.type == MediaType.ANIME

    def test_empty_media_type_is_normalized_for_metadata_lookup(self):
        """未选择类型时前端可能传空串，SearchQuery 枚举不接受空串."""
        orchestrator = MagicMock()
        orchestrator.resolve_content_id_media.return_value = None
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        fn = make_web_search_fn(orchestrator, system_config=None)
        fn(
            "DEMO-4025269",
            anchor_provider="content_id",
            anchor_external_id="DEMO-4025269",
            content_profile="demo",
            media_type="",
        )
        kwargs = orchestrator.resolve_content_id_media.call_args.kwargs
        assert kwargs["media_type"] is None

    def test_default_sites_applied(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        system_config = MagicMock()
        system_config.get.return_value = {"search_sites": ["site_a"]}
        fn = make_web_search_fn(orchestrator, system_config=system_config)
        fn("x", media_type=MediaType.TV)
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["site"] == ["site_a"]

    def test_default_first_creates_site_tier(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        system_config = MagicMock()
        system_config.get.return_value = {"search_sites": ["site_a"]}
        fn = make_web_search_fn(orchestrator, system_config=system_config)
        fn(
            "x",
            media_type=MediaType.MOVIE,
            filters={"site_default_first": True, "site_fallback": ["site_b"]},
        )
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["site"] == ["site_a", "site_b"]
        assert ctx.filter_args["site_tier"] == ["site_a"]

    def test_explicit_sites_not_overridden(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        system_config = MagicMock()
        system_config.get.return_value = {}
        fn = make_web_search_fn(orchestrator, system_config=system_config)
        fn("x", filters={"site": ["manual"]})
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["site"] == ["manual"]

    def test_empty_site_list_means_all_sites(self):
        """前端未选择站点时传空数组 → 归一为 None（全部可见站点，含第三方索引器）

        回归：此前搜索页省略 site 字段，后端转而套用默认订阅设置的 search_sites，
        第三方索引器站点被排除，与 UI「全部已授权站点」文案不符。
        """
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        system_config = MagicMock()
        system_config.get.return_value = {"search_sites": ["only_default"]}
        fn = make_web_search_fn(orchestrator, system_config=system_config)
        fn("x", filters={"site": []}, media_type=MediaType.TV)
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["site"] is None


class TestProviderTitleMatch:
    def test_wrong_tmdb_title_is_rejected(self):
        media = SimpleNamespace(provider_data={"name": "The Private Navy of Sgt. O'Farrell"})
        assert not SearchOrchestrator._provider_title_matches(media, "凡人修仙传")

    def test_title_and_alias_are_accepted(self):
        media = SimpleNamespace(
            provider_data={
                "name": "A Record Of A Mortals Journey To Immortality",
                "aliases": ["凡人修仙传"],
            }
        )
        assert SearchOrchestrator._provider_title_matches(media, "凡人修仙传")

    def test_identity_matches_rejects_stale_anchor(self):
        media = SimpleNamespace(
            title="The Private Navy of Sgt. O'Farrell",
            cn_name=None,
            en_name=None,
            original_title=None,
            aliases=[],
            provider_data=None,
        )
        assert not SearchOrchestrator.identity_matches_keyword(media, "凡人修仙传")
        assert SearchOrchestrator.identity_matches_keyword(media, "Private Navy")

    def test_tmdb_as_obj_provider_data_is_supported(self):
        media = SimpleNamespace(provider_data=AsObj(name="凡人修仙传", original_name="凡人修仙传"))

        assert SearchOrchestrator._provider_title(media) == "凡人修仙传"
        assert SearchOrchestrator._provider_title_matches(media, "凡人修仙传")
