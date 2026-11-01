"""Web 搜索统一入口（make_web_search_fn）单元测试"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.infrastructure.external.tmdbv3api.as_obj import AsObj
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

    def test_default_sites_applied(self):
        orchestrator = MagicMock()
        orchestrator.orchestrate.return_value = (None, {}, 1, 0)
        system_config = MagicMock()
        system_config.get.return_value = {"search_sites": ["site_a"]}
        fn = make_web_search_fn(orchestrator, system_config=system_config)
        fn("x", media_type=MediaType.TV)
        ctx = orchestrator.orchestrate.call_args[0][0]
        assert ctx.filter_args["site"] == ["site_a"]

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
