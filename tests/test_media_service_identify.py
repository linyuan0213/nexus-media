"""
MediaService.identify 单元测试 — 验证缓存、strict、language 参数
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

# mock log 避免加载真实日志模块
sys.modules['log'] = MagicMock()

# 现在可以安全导入被测代码
from app.media.lookup.tmdb_lookup import TmdbLookup
from app.media.models import MediaInfo
from app.media.parser.base import ParserResult
from app.media.service import MediaService
from app.utils.types import MatchMode, MediaType


class TestMediaServiceIdentify:
    @pytest.fixture
    def service(self):
        with patch.object(MediaService, '_init_config'):
            svc = MediaService()
            svc._rmt_match_mode = MatchMode.NORMAL
            svc._search_tmdbweb = False
            svc._ai_enable = False
            svc._search_keyword = False
            svc._episode_mapping_enabled = False
            svc._parser = MagicMock()
            svc._lookup = MagicMock()
            svc._episode_mapper = MagicMock()
            return svc

    def test_identify_cache_hit(self, service):
        """缓存命中时直接返回，不走 TMDB 查询"""
        cached = MediaInfo(tmdb_id=123, title="Cached", year="2024", type=MediaType.MOVIE)
        service._lookup.client.redis_cache.get_media_info.return_value = cached
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )

        result = service.identify("Test.2024.1080p.mkv")

        assert result is cached
        service._lookup.lookup.assert_not_called()

    def test_identify_cache_miss(self, service):
        """缓存未命中时走正常查询流程"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )
        mock_result = MagicMock()
        mock_result.tmdb_id = 456
        mock_result.title = "Test Movie"
        mock_result.year = "2024"
        mock_result.media_type = MediaType.MOVIE
        mock_result.genres = ["Action"]
        service._lookup.lookup.return_value = mock_result
        service._lookup.get_tmdb_info.return_value = None

        result = service.identify("Test.2024.1080p.mkv")

        assert result.tmdb_id == 456
        service._lookup.lookup.assert_called_once()
        # 验证缓存写入
        service._lookup.client.redis_cache.set_media_info.assert_called_once()

    def test_identify_strict_true_no_year_fallback(self, service):
        """strict=True 时，TV 不会去掉年份再查"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Show", year="2024", type=MediaType.TV
        )
        service._lookup.lookup.return_value = None

        service.identify("Show.2024.S01E01.mkv", strict=True)

        call_args = service._lookup.lookup.call_args
        assert call_args.kwargs.get("strict") is True

    def test_identify_strict_false_allows_year_fallback(self, service):
        """strict=False 时，TV 允许去掉年份再查（NORMAL 模式）"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Show", year="2024", type=MediaType.TV
        )
        service._lookup.lookup.return_value = None

        service.identify("Show.2024.S01E01.mkv", strict=False)

        call_args = service._lookup.lookup.call_args
        assert call_args.kwargs.get("strict") is False

    def test_identify_strict_none_uses_config_mode(self, service):
        """strict=None 时，使用配置中的 match_mode"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Show", year="2024", type=MediaType.TV
        )
        service._lookup.lookup.return_value = None

        # NORMAL 模式
        service._rmt_match_mode = MatchMode.NORMAL
        service.identify("Show.2024.S01E01.mkv", strict=None)
        assert service._lookup.lookup.call_args.kwargs.get("strict") is False

        # STRICT 模式
        service._rmt_match_mode = MatchMode.STRICT
        service.identify("Show.2024.S01E01.mkv", strict=None)
        assert service._lookup.lookup.call_args.kwargs.get("strict") is True

    def test_identify_language_passed_to_lookup(self, service):
        """language 参数应传递到 lookup 和 client.set_language"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )
        service._lookup.lookup.return_value = None

        service.identify("Test.2024.1080p.mkv", language="en")

        service._lookup.client.set_language.assert_any_call("en")
        call_args = service._lookup.lookup.call_args
        assert call_args.kwargs.get("language") == "en"

    def test_identify_cache_disabled(self, service):
        """cache=False 时不读缓存也不写缓存"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )
        service._lookup.lookup.return_value = None

        service.identify("Test.2024.1080p.mkv", cache=False)

        service._lookup.client.redis_cache.get_media_info.assert_not_called()
        service._lookup.client.redis_cache.set_media_info.assert_not_called()

    def test_identify_append_to_response_passed(self, service):
        """append_to_response 应传递到 get_tmdb_info"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )
        mock_result = MagicMock()
        mock_result.tmdb_id = 456
        mock_result.media_type = MediaType.MOVIE
        mock_result.genres = []  # 空 genres 会触发 get_tmdb_info
        service._lookup.lookup.return_value = mock_result

        service.identify("Test.2024.1080p.mkv", append_to_response="credits")

        service._lookup.get_tmdb_info.assert_called_once()
        call_args = service._lookup.get_tmdb_info.call_args
        assert call_args.kwargs.get("append_to_response") == "credits"

    def test_identify_old_cache_ignored(self, service):
        """缓存中的旧 MetaInfo 对象应被忽略（等待 TTL 过期）"""
        old_meta = MagicMock()  # 模拟旧 MetaInfo 对象
        old_meta.tmdb_id = 123
        service._lookup.client.redis_cache.get_media_info.return_value = old_meta
        service._parser.parse.return_value = ParserResult(
            title_en="Test", year="2024", type=MediaType.MOVIE
        )
        mock_result = MagicMock()
        mock_result.tmdb_id = 456
        mock_result.media_type = MediaType.MOVIE
        mock_result.genres = ["Action"]
        service._lookup.lookup.return_value = mock_result
        service._lookup.get_tmdb_info.return_value = None

        result = service.identify("Test.2024.1080p.mkv")

        assert result.tmdb_id == 456  # 旧缓存未命中，走了正常查询
        service._lookup.lookup.assert_called_once()

    def test_merge_media_info_year(self, service):
        """merge_media_info 应合并 year 字段"""
        target = MediaInfo(title="Target", year=None, tmdb_id=1)
        source = MediaInfo(title="Source", year="2026", tmdb_id=2)
        result = TmdbLookup.merge_media_info(target, source)
        assert result.year == "2026"
        assert result.title == "Source"  # source 优先覆盖 target

    def test_identify_batch_no_mapping_for_movies(self, service):
        """identify_batch: 电影不应触发 EpisodeMapper"""
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse_batch.return_value = [
            ParserResult(title_en="Movie", year="2024", type=MediaType.MOVIE),
        ]
        mock_result = MagicMock()
        mock_result.tmdb_id = 101
        mock_result.media_type = MediaType.MOVIE
        service._lookup.lookup.return_value = mock_result

        results = service.identify_batch([{"title": "Movie.2024.mkv"}])

        assert len(results) == 1
        assert results[0].tmdb_id == 101
        service._episode_mapper.map_batch.assert_not_called()

    def test_identify_batch_episode_mapping(self, service):
        """identify_batch: 动漫合并季应触发集数映射"""
        service._episode_mapping_enabled = True
        service._lookup.client.redis_cache.get_media_info.return_value = None
        service._parser.parse_batch.return_value = [
            ParserResult(title_en="Anime", year="2021", type=MediaType.ANIME,
                         season=4, episode=2),
        ]
        mock_result = MagicMock()
        mock_result.tmdb_id = 202
        mock_result.media_type = MediaType.TV
        service._lookup.lookup.return_value = mock_result
        service._episode_mapper.map_batch.return_value = [(1, 68)]

        results = service.identify_batch([{"title": "Anime.S04E02.mkv"}])

        assert len(results) == 1
        assert results[0].tmdb_id == 202
        assert results[0].begin_season == 1
        assert results[0].begin_episode == 68
        service._episode_mapper.map_batch.assert_called_once()

    def test_identify_files_with_tmdb_info_mapping(self, service):
        """identify_files: 传入 tmdb_info 时也应支持 EpisodeMapper"""
        service._episode_mapping_enabled = True
        service._parser.parse.return_value = ParserResult(
            title_en="Anime", year="2021", type=MediaType.ANIME,
            season=3, episode=5
        )
        service._episode_mapper.map_batch.return_value = [(1, 45)]

        tmdb_info = {"id": 303, "media_type": MediaType.TV}
        with patch('os.path.exists', return_value=True):
            result = service.identify_files(
                ["/media/Anime.S03E05.mkv"],
                tmdb_info=tmdb_info
            )

        assert "/media/Anime.S03E05.mkv" in result
        info = result["/media/Anime.S03E05.mkv"]
        assert info.tmdb_id == 303
        assert info.begin_season == 1
        assert info.begin_episode == 45
        service._episode_mapper.map_batch.assert_called_once()

    def test_identify_files_without_mapping_disabled(self, service):
        """identify_files: EpisodeMapper 禁用时跳过映射"""
        service._episode_mapping_enabled = False
        service._parser.parse.return_value = ParserResult(
            title_en="Anime", year="2021", type=MediaType.ANIME,
            season=3, episode=5
        )

        tmdb_info = {"id": 303, "media_type": MediaType.TV}
        with patch('os.path.exists', return_value=True):
            result = service.identify_files(
                ["/media/Anime.S03E05.mkv"],
                tmdb_info=tmdb_info
            )

        assert "/media/Anime.S03E05.mkv" in result
        info = result["/media/Anime.S03E05.mkv"]
        assert info.begin_season == 3
        assert info.begin_episode == 5
        service._episode_mapper.map_batch.assert_not_called()
