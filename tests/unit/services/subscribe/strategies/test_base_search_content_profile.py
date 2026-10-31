"""BaseSearchStrategy._get_media_info 画像分支单元测试.

回归：`content_profile="anime"` 的订阅曾被 `content_profile not in ("", "default")`
判断归入"非核心画像"分支，跳过 TMDB 查询（tmdb_id 被清空、en_name/provider_data
未填充），导致后续 quick_name_match 把该订阅的所有种子判定为不匹配，
出现"原始结果 200 条、有效资源数 0"的现象。

`anime` 属于核心画像（同文件 _get_media_info 的注释与另一处判断均已包含 anime），
应与其他核心画像一样查询 TMDB。
"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.services.subscribe.strategies.base_search import BaseSearchStrategy

# 带 media_type 与海报的 TMDB 详情，供 set_provider_data/get_poster_image 使用
_TMDB_TV = {
    "id": 106449,
    "name": "凡人修仙传",
    "media_type": "tv",
    "poster_path": "/u1VRjvvCIVwb1MUhoxSAUimhoKZ.jpg",
    "seasons": [{"season_number": 1}],
}


def _make_strategy(tmdb_info=None):
    """构造仅含 _get_media_info 所需依赖的策略实例（绕开 __init__ 的仓储初始化）。"""
    s = object.__new__(BaseSearchStrategy)
    s._ident_cache = MagicMock()
    s._ident_cache.get.return_value = None
    s._media_cache = MagicMock()
    s._media_cache.get_tmdb_info.return_value = tmdb_info
    s._media_service = MagicMock()
    # identify 兜底在缺少海报时触发；返回 None 表示无需替换，保持被测路径纯净
    s._media_service.identify.return_value = None
    s._media_service.enrich_en_name.side_effect = lambda mi: setattr(
        mi, "en_name", mi.en_name or "A Record Of A Mortals Journey To Immortality"
    )
    return s


@pytest.fixture(autouse=True)
def _isolate_category_repo():
    """隔离分类仓储：set_provider_data 会读取 CONFIG_CATEGORY 推断画像，测试中置空。"""
    with patch(
        "app.db.repositories.category_repo_adapter.CategoryConfigRepositoryAdapter.get_all",
        return_value=[],
    ):
        yield


class TestGetMediaInfoContentProfile:
    """验证不同 content_profile 下是否查询 TMDB。"""

    def test_anime_profile_queries_tmdb(self):
        """anime 画像必须查询 TMDB，并写入 tmdb_id 与 provider_data。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.ANIME,
            content_profile="anime",
        )

        # 关键断言：anime 画像应保留 tmdb_id 并填充 provider_data
        assert info is not None
        assert str(info.tmdb_id) == "106449"
        assert info.provider_data
        strategy._media_cache.get_tmdb_info.assert_called_once()

    def test_anime_profile_gets_english_name(self):
        """anime 画像应补全英文名，避免 quick_name_match 因缺英文名拒绝种子。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.ANIME,
            content_profile="anime",
        )

        assert info is not None
        assert info.en_name
        strategy._media_service.enrich_en_name.assert_called_once()

    def test_default_profile_queries_tmdb(self):
        """default 画像保持原有行为（查询 TMDB）。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.TV,
            content_profile="default",
        )

        assert info is not None
        assert str(info.tmdb_id) == "106449"
        assert info.provider_data

    def test_empty_profile_queries_tmdb(self):
        """空画像等同 default，查询 TMDB。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.TV,
            content_profile="",
        )

        assert info is not None
        assert str(info.tmdb_id) == "106449"

    def test_custom_profile_skips_tmdb(self):
        """插件自定义画像不查询 TMDB，由插件提供元数据。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.ANIME,
            content_profile="plugin_custom",
        )

        assert info is not None
        # 自定义画像分支会清空 tmdb_id，且不调用 TMDB
        assert info.tmdb_id == ""
        strategy._media_cache.get_tmdb_info.assert_not_called()

    @pytest.mark.parametrize("profile", ["Anime", "ANIME"])
    def test_anime_profile_case_insensitive(self, profile):
        """画像名大小写不影响判定（Anime / ANIME 均视为核心画像）。"""
        strategy = _make_strategy(dict(_TMDB_TV))

        info = strategy._get_media_info(
            tmdbid="106449",
            name="凡人修仙传",
            year="2020",
            mtype=MediaType.ANIME,
            content_profile=profile,
        )

        assert info is not None
        assert str(info.tmdb_id) == "106449"
        strategy._media_cache.get_tmdb_info.assert_called_once()
