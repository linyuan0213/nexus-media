import pytest

from app.media.models import MediaInfo
from app.media.parser.base import ParserResult
from app.media.parser.regex import RegexParser
from app.utils.types import MediaType


class TestParserResult:
    def test_default_values(self):
        result = ParserResult()
        assert result.confidence == 0.0
        assert result.type is None

    def test_full_values(self):
        result = ParserResult(
            title_en="Test Movie",
            title_cn="测试电影",
            year="2024",
            season=1,
            episode=3,
            resource_pix="1080p",
            video_encode="H264",
            audio_encode="AAC",
            resource_team="TestGroup",
            type=MediaType.MOVIE,
            confidence=0.9,
        )
        assert result.title_en == "Test Movie"
        assert result.season == 1
        assert result.confidence == 0.9


class TestRegexParser:
    def test_parse_movie(self):
        parser = RegexParser()
        result = parser.parse("The.Matrix.1999.1080p.BluRay.x264.mkv")
        assert result is not None
        assert result.type == MediaType.MOVIE
        assert result.year == "1999"

    def test_parse_tv(self):
        parser = RegexParser()
        result = parser.parse("Breaking.Bad.S01E03.1080p.mkv")
        assert result is not None
        assert result.type == MediaType.TV
        assert result.season == 1
        assert result.episode == 3

    def test_parse_batch(self):
        parser = RegexParser()
        titles = [
            "Movie.A.2024.1080p.mkv",
            "Show.S01E01.1080p.mkv",
        ]
        results = parser.parse_batch(titles)
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is not None

    def test_parse_invalid(self):
        parser = RegexParser()
        result = parser.parse("")
        assert result is None


class TestMediaInfo:
    def test_from_parser(self):
        parsed = ParserResult(
            title_cn="测试",
            title_en="Test",
            year="2024",
            season=1,
            episode=5,
            type=MediaType.TV,
        )
        info = MediaInfo.from_parser(parsed)
        assert info.cn_name == "测试"
        assert info.begin_season == 1
        assert info.begin_episode == 5
        assert info.type == MediaType.TV
        assert info.end_season is None
        assert info.end_episode is None
        assert info.get_season_string() == "S01"
        assert info.get_episode_string() == "E05"
        assert info.get_season_episode_string() == "S01 E05"

    def test_get_name_chinese_priority(self):
        info = MediaInfo(cn_name="中文名", en_name="English Name")
        assert info.get_name() == "中文名"

    def test_get_season_string(self):
        info = MediaInfo(begin_season=1, end_season=3, type=MediaType.TV)
        assert info.get_season_string() == "S01-S03"

    def test_get_season_string_single(self):
        info = MediaInfo(begin_season=2, type=MediaType.TV)
        assert info.get_season_string() == "S02"

    def test_is_in_season(self):
        info = MediaInfo(begin_season=1, end_season=3, type=MediaType.TV)
        assert info.is_in_season(2) is True
        assert info.is_in_season(5) is False

    def test_is_in_episode(self):
        info = MediaInfo(begin_episode=1, end_episode=10, type=MediaType.TV)
        assert info.is_in_episode(5) is True
        assert info.is_in_episode(15) is False

    def test_to_dict(self):
        info = MediaInfo(tmdb_id=123, title="Test", year="2024")
        d = info.to_dict()
        assert d["tmdb_id"] == 123
        assert d["title"] == "Test"
