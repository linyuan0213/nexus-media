"""订阅类型推断 / 探索页订阅标识匹配 / 缓存未命中回源识别 测试."""

from unittest.mock import MagicMock

import app.services.subscribe.management.query_service as query_service_module
from app.domain.media_utils import check_media_exists
from app.domain.mediatypes import MediaType
from app.services.subscribe.management.query_service import _resolve_subscribe_type
from app.services.subscribe.strategies.base_search import BaseSearchStrategy


class TestResolveSubscribeType:
    @staticmethod
    def _patch_cache(monkeypatch, genres):
        cache = MagicMock()
        cache.get_tmdb_info.return_value = {"genres": genres} if genres is not None else None
        monkeypatch.setattr(query_service_module, "TMDBCache", lambda: cache)

    def test_explicit_types_kept(self, monkeypatch):
        self._patch_cache(monkeypatch, None)
        assert _resolve_subscribe_type("anime") == "anime"
        assert _resolve_subscribe_type("movie") == "movie"
        assert _resolve_subscribe_type("tv") == "tv"

    def test_missing_note_infers_anime_from_tmdb(self, monkeypatch):
        """历史订阅 NOTE 无 media_type：按 TMDB genre 16 推断为动漫."""
        self._patch_cache(monkeypatch, [{"id": 16, "name": "Animation"}])
        assert _resolve_subscribe_type(None, 258348) == "anime"

    def test_missing_note_non_anime_defaults_tv(self, monkeypatch):
        self._patch_cache(monkeypatch, [{"id": 35, "name": "Comedy"}])
        assert _resolve_subscribe_type(None, 94664) == "tv"

    def test_missing_note_without_tmdb_defaults_tv(self, monkeypatch):
        self._patch_cache(monkeypatch, None)
        assert _resolve_subscribe_type(None, None) == "tv"

    def test_non_dict_cache_object_supported(self, monkeypatch):
        """缓存值为 tmdbv3api AsObj（支持 .get 的映射对象）时同样能判定动漫."""

        class _AsObj:
            def __init__(self, genres):
                self._genres = genres

            def get(self, key, default=None):
                return self._genres if key == "genres" else default

        class _Genre:
            def __init__(self, gid):
                self._id = gid

            def get(self, key, default=None):
                return self._id if key == "id" else default

        cache = MagicMock()
        cache.get_tmdb_info.return_value = _AsObj([_Genre(16), _Genre(10759)])
        monkeypatch.setattr(query_service_module, "TMDBCache", lambda: cache)
        assert _resolve_subscribe_type(None, 258348) == "anime"


class TestCheckMediaExistsRawTitleFallback:
    def test_falls_back_to_raw_title_without_year_suffix(self):
        """电视剧会追加 " (year)"，回退必须用原始标题，否则永远匹配不到订阅."""
        media_server = MagicMock()
        media_server.check_item_exists.return_value = False
        media_server.check_library_present.return_value = False
        subscribe = MagicMock()
        subscribe.get_subscribe_id.side_effect = lambda **kw: 42 if kw["title"] == "克雷瓦提斯" else None

        fav, rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="克雷瓦提斯",
            year="2025",
            mediaid="258348",
        )

        assert fav == "1"
        assert rssid == 42
        calls = subscribe.get_subscribe_id.call_args_list
        assert calls[0].kwargs["title"] == "克雷瓦提斯 (2025)"
        assert calls[1].kwargs["title"] == "克雷瓦提斯"


class TestGetMediaInfoReidentify:
    def test_reidentify_when_cache_miss(self):
        """TMDB 缓存过期（tmdb_info 为空）时必须回源识别，而不是判为识别失败."""
        strategy = BaseSearchStrategy.__new__(BaseSearchStrategy)
        strategy._ident_cache = MagicMock()
        strategy._ident_cache.get.return_value = None
        strategy._media_cache = MagicMock()
        strategy._media_cache.get_tmdb_info.return_value = None
        identified = MagicMock()
        identified.tmdb_info = {"id": 258348}
        identified.get_poster_image.return_value = "poster.jpg"
        strategy._media_service = MagicMock()
        strategy._media_service.identify.return_value = identified

        info = strategy._get_media_info(258348, "克雷瓦提斯", "2025", MediaType.TV)

        assert info is identified
        strategy._media_service.identify.assert_called_once()


class TestSubscribeTitleFuzzyMatch:
    """豆瓣/探索页标题与订阅名不一致时的匹配（双向包含 + 归一化 + 相似度）."""

    def test_bidirectional_normalized_match(self):
        from app.db.repositories.subscribe_repository import SubscribeRepository

        assert SubscribeRepository._titles_match(
            "无职转生～到了异世界就拿出真本事～", "无职转生Ⅲ 到了异世界就拿出真本事"
        )
        assert SubscribeRepository._titles_match("克雷瓦提斯-魔兽之王与婴儿与尸之勇者-", "克雷瓦提斯")

    def test_similarity_match(self):
        from app.db.repositories.subscribe_repository import SubscribeRepository

        assert SubscribeRepository._titles_match(
            "虽然我是不完美恶女～雏宫蝶鼠替换传～", "虽然我不是完美恶女～雏宫蝶鼠替换传～"
        )

    def test_unrelated_titles_do_not_match(self):
        from app.db.repositories.subscribe_repository import SubscribeRepository

        assert not SubscribeRepository._titles_match("猫与龙", "尼古喵喵")
        assert not SubscribeRepository._titles_match("", "克雷瓦提斯")


class TestCompletedSubscriptionBadge:
    """已完成订阅（历史记录）应显示"已入库"（媒体库同步库为空的兜底）."""

    def test_history_hit_returns_in_library(self):
        media_server = MagicMock()
        media_server.check_item_exists.return_value = None
        media_server.check_library_present.return_value = False
        subscribe = MagicMock()
        subscribe.get_subscribe_id.side_effect = None
        subscribe.get_subscribe_id.return_value = None
        subscribe.get_subscribe_id_by_alias.return_value = None
        subscribe.get_history_id.return_value = 7

        fav, rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="穹庐下的魔女",
            year="2026",
            mediaid="DB:37315819",
        )

        assert fav == "2"
        assert rssid == "7"

    def test_active_subscription_wins_over_library(self):
        """订阅中应显示"已订阅"，不被"已入库"覆盖（库里有该剧时同样如此）."""
        media_server = MagicMock()
        media_server.check_item_exists.return_value = None
        media_server.check_library_present.return_value = True
        subscribe = MagicMock()
        subscribe.get_subscribe_id.side_effect = lambda **kw: 20 if kw["title"].startswith("描绘直至生命尽头") else None

        fav, rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="描绘直至生命尽头",
            year="2026",
            mediaid="DB:37514162",
        )

        assert fav == "1"
        assert rssid == 20
        media_server.check_library_present.assert_not_called()

    def test_active_subscription_prefers_subscribed(self):
        media_server = MagicMock()
        media_server.check_item_exists.return_value = None
        media_server.check_library_present.return_value = False
        subscribe = MagicMock()
        subscribe.get_subscribe_id.side_effect = lambda **kw: 12 if kw["title"].startswith("尼古喵喵") else None
        subscribe.get_history_id.return_value = 7

        fav, rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="尼古喵喵",
            year="2026",
            mediaid="DB:38194261",
        )

        assert fav == "1"
        assert rssid == 12
        subscribe.get_history_id.assert_not_called()


class TestLiveLibraryFallback:
    """同步登记薄为空时，回退实时查询媒体服务器也应判为已入库."""

    def test_live_check_marks_in_library(self):
        media_server = MagicMock()
        media_server.check_item_exists.return_value = None
        media_server.check_library_present.return_value = True
        subscribe = MagicMock()
        subscribe.get_subscribe_id.side_effect = None
        subscribe.get_subscribe_id.return_value = None
        subscribe.get_subscribe_id_by_alias.return_value = None
        subscribe.get_history_id.return_value = None

        fav, _rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="穹庐下的魔女",
            year="2026",
            mediaid="DB:37315819",
        )

        assert fav == "2"
        media_server.check_library_present.assert_called_once()


class TestSubscribeAliasMatch:
    """BGM/豆瓣名称与订阅名不同时，按 TMDB 别名匹配为"已订阅"."""

    @staticmethod
    def _service(alias_map: dict[int, list[str]], subs: dict):
        import app.services.subscribe.management.service as svc_mod

        svc_mod._ALIAS_MAP_CACHE.clear()
        svc = svc_mod.SubscribeService.__new__(svc_mod.SubscribeService)
        media = MagicMock()
        media.get_all_names.side_effect = lambda tmdbid, mtype: alias_map.get(tmdbid, [])

        def _tvs(*_a, **_kw):
            return subs

        setattr(svc, "_media", media)
        setattr(svc, "get_subscribe_tvs", _tvs)
        setattr(svc, "get_subscribe_movies", lambda *_a, **_kw: {})
        return svc, media

    def test_alias_resolves_to_subscription(self):
        svc, media = self._service(
            {287028: ["描绘直至生命尽头", "画完这个再去死"]},
            {"20": {"tmdbid": "287028"}},
        )

        assert svc.get_subscribe_id_by_alias("画完这个再去死", MediaType.TV) == 20
        # 二次查询命中缓存，不再请求 TMDB 别名
        assert svc.get_subscribe_id_by_alias("描绘直至生命尽头", MediaType.TV) == 20
        assert media.get_all_names.call_count == 1

    def test_alias_returns_none_when_unknown(self):
        svc, _media = self._service({}, {"20": {"tmdbid": "287028"}})
        assert svc.get_subscribe_id_by_alias("不存在的别名", MediaType.TV) is None


class TestAliasFallbackInCheckMediaExists:
    def test_alias_hit_returns_subscribed(self):
        media_server = MagicMock()
        media_server.check_item_exists.return_value = None
        media_server.check_library_present.return_value = True
        subscribe = MagicMock()
        subscribe.get_subscribe_id.return_value = None
        subscribe.get_subscribe_id_by_alias.return_value = 20

        fav, rssid, _ = check_media_exists(
            media_server=media_server,
            subscribe=subscribe,
            mtype="tv",
            title="画完这个再去死",
            year="2026",
            mediaid="BG:123456",
        )

        assert fav == "1"
        assert rssid == 20
        media_server.check_item_exists.assert_not_called()
