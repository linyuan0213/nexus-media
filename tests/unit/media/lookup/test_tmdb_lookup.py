"""TMDB lookup 工具函数测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.lookup.tmdb_lookup import TmdbLookup
from app.media.models import MediaInfo
from app.media.parser import RegexParser
from app.media.parser.base import ParserResult


class TestNegativeLookupCache:
    """未命中结果应被负缓存，避免每次重复查 TMDB."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        cache = get_cache_manager().get("tmdb_lookup")
        if cache is not None:
            cache.clear()

    def test_not_found_is_cached(self):
        parser = RegexParser()
        lookup = TmdbLookup(client=MagicMock())
        parsed = parser.parse("NegativeCacheOnlyTitle 1999")
        assert parsed is not None

        with patch.object(lookup, "_lookup_tmdb", return_value=None) as mock_lookup:
            assert lookup.lookup(parsed) is None
            assert mock_lookup.call_count >= 1
            first_call_count = mock_lookup.call_count

            # 第二次应命中负缓存，不再发起查询
            assert lookup.lookup(parsed) is None
            assert mock_lookup.call_count == first_call_count

    def test_negative_cache_expires(self):
        parser = RegexParser()
        lookup = TmdbLookup(client=MagicMock())
        parsed = parser.parse("NegativeCacheExpireTitle 2001")
        assert parsed is not None

        with patch.object(lookup, "_lookup_tmdb", return_value=None) as mock_lookup:
            assert lookup.lookup(parsed) is None
            first_call_count = mock_lookup.call_count

            # 直接改写缓存 TTL 为 0 模拟过期
            key = (
                f"lookup:{parsed.title_cn or ''}|{parsed.title_en or ''}|{parsed.year or ''}"
                f"|{parsed.season or ''}|{parsed.type.value if parsed.type else ''}|"
            )
            lookup._lookup_cache.set(key, False, ttl=0)
            assert lookup.lookup(parsed) is None
            assert mock_lookup.call_count > first_call_count


class TestTrimmedTailRetry:
    """标题尾部残留标签导致整名搜不到时，应裁剪尾词重试."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        cache = get_cache_manager().get("tmdb_lookup")
        if cache is not None:
            cache.clear()

    @staticmethod
    def _parsed(title_en, year="2026", mtype=MediaType.MOVIE):
        return ParserResult(title_en=title_en, year=year, type=mtype)

    def test_trim_tail_finds_match(self):
        lookup = TmdbLookup(client=MagicMock())
        parsed = self._parsed("The Of Oak Street Ma")
        searched: list[str] = []

        def fake_search_movie(name, year=None):
            searched.append(name)
            if name == "The Of Oak Street":
                return {
                    "id": 1101383,
                    "title": "The Of Oak Street",
                    "release_date": "2026-01-01",
                    "media_type": MediaType.MOVIE,
                    "genres": [{"id": 18}],
                }
            return {}

        with (
            patch.object(lookup, "_lookup_tmdb", return_value=None),
            patch.object(lookup.search, "search_movie", side_effect=fake_search_movie),
        ):
            result = lookup.lookup(parsed)

        assert result is not None
        assert result.tmdb_id == 1101383
        assert searched == ["The Of Oak Street"]

    def test_trim_tail_rejects_name_mismatch(self):
        lookup = TmdbLookup(client=MagicMock())
        parsed = self._parsed("Unrelated Query Title Ma")

        def fake_search_movie(name, year=None):
            return {
                "id": 7,
                "title": "Completely Different Movie",
                "release_date": "2026-01-01",
                "media_type": MediaType.MOVIE,
                "genres": [{"id": 18}],
            }

        with (
            patch.object(lookup, "_lookup_tmdb", return_value=None),
            patch.object(lookup.search, "search_movie", side_effect=fake_search_movie),
            patch.object(lookup.search, "search_tv", return_value={}),
            patch.object(lookup.search, "search_multi", return_value={}),
        ):
            assert lookup.lookup(parsed) is None

    def test_trim_tail_rejects_year_conflict(self):
        lookup = TmdbLookup(client=MagicMock())
        parsed = self._parsed("Some Real Title Ma")

        def fake_search_movie(name, year=None):
            return {
                "id": 8,
                "title": "Some Real Title",
                "release_date": "1995-01-01",
                "media_type": MediaType.MOVIE,
                "genres": [{"id": 18}],
            }

        with (
            patch.object(lookup, "_lookup_tmdb", return_value=None),
            patch.object(lookup.search, "search_movie", side_effect=fake_search_movie),
            patch.object(lookup.search, "search_tv", return_value={}),
            patch.object(lookup.search, "search_multi", return_value={}),
        ):
            assert lookup.lookup(parsed) is None

    def test_strict_mode_skips_trim_tail(self):
        lookup = TmdbLookup(client=MagicMock())
        parsed = self._parsed("Strict Mode Title Ma")
        searched: list[str] = []

        def fake_search_movie(name, year=None):
            searched.append(name)
            return {}

        with (
            patch.object(lookup, "_lookup_tmdb", return_value=None),
            patch.object(lookup.search, "search_movie", side_effect=fake_search_movie),
        ):
            assert lookup.lookup(parsed, strict=True) is None
        assert searched == []


class TestMergeMediaInfo:
    """测试 merge_media_info 合并媒体信息."""

    def test_merge_media_info_copies_image_fields(self):
        """搜索结果缺少图片时应从原始匹配媒体复制图片字段."""
        target = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            year="2026",
            tmdb_id=123456,
        )
        source = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            year="2026",
            tmdb_id=123456,
            poster_path="https://image.tmdb.org/t/p/w500/abc.jpg",
            backdrop_path="https://image.tmdb.org/t/p/w1280/xyz.jpg",
            fanart_backdrop="https://fanart.tv/123.jpg",
        )

        result = TmdbLookup.merge_media_info(target, source)

        assert result.poster_path == "https://image.tmdb.org/t/p/w500/abc.jpg"
        assert result.backdrop_path == "https://image.tmdb.org/t/p/w1280/xyz.jpg"
        assert result.fanart_backdrop == "https://fanart.tv/123.jpg"

    def test_merge_media_info_keeps_target_image(self):
        """目标本身有图片时保留目标的图片."""
        target = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            poster_path="https://target.poster.jpg",
        )
        source = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            poster_path="https://source.poster.jpg",
        )

        result = TmdbLookup.merge_media_info(target, source)

        assert result.poster_path == "https://target.poster.jpg"

    def test_merge_media_info_returns_target_when_source_is_none(self):
        """source 为空时返回 target."""
        target = MediaInfo(title="Test", type=MediaType.MOVIE)
        assert TmdbLookup.merge_media_info(target, None) is target

    def test_merge_media_info_returns_target_when_target_is_none(self):
        """target 为空时返回 target."""
        source = MediaInfo(title="Test", type=MediaType.MOVIE)
        assert TmdbLookup.merge_media_info(None, source) is None
