from unittest.mock import patch

from app.media.parser.base import BaseParser, ParserResult
from app.media.parser.llm import LLMParser
from app.utils.types import MediaType


class TestLLMParser:
    """LLMParser 单元测试 — 验证接口契约和降级行为"""

    def test_implements_base_parser(self):
        """LLMParser 必须实现 BaseParser 接口"""
        parser = LLMParser()
        assert isinstance(parser, BaseParser)

    def test_ready_false_when_recognizer_not_ready(self):
        """MediaRecognizer 未就绪时 ready 为 False"""
        with patch("app.media.parser.llm.MediaRecognizer") as mock_rec:
            mock_rec.return_value.ready = False
            parser = LLMParser()
            assert parser.ready is False

    def test_parse_returns_none_when_not_ready(self):
        """ready=False 时 parse() 返回 None"""
        with patch("app.media.parser.llm.MediaRecognizer") as mock_rec:
            mock_inst = mock_rec.return_value
            mock_inst.ready = False
            mock_inst.recognize.return_value = None
            parser = LLMParser()
            result = parser.parse("[ANi] Test Anime - 03 [1080P][Baha][WEB-DL]")
            assert result is None

    def test_parse_batch_returns_none_list_when_not_ready(self):
        """ready=False 时 parse_batch() 返回全 None 列表"""
        with patch("app.media.parser.llm.MediaRecognizer") as mock_rec:
            mock_inst = mock_rec.return_value
            mock_inst.ready = False
            mock_inst.recognize_batch.return_value = [None, None, None]
            parser = LLMParser()
            results = parser.parse_batch(["Title1", "Title2", "Title3"])
            assert len(results) == 3
            assert all(r is None for r in results)

    def test_map_type_anime(self):
        """_map_type 正确映射 anime"""
        assert LLMParser._map_type("anime") == MediaType.ANIME

    def test_map_type_tv(self):
        """_map_type 正确映射 tv"""
        assert LLMParser._map_type("tv") == MediaType.TV

    def test_map_type_movie(self):
        """_map_type 正确映射 movie"""
        assert LLMParser._map_type("movie") == MediaType.MOVIE

    def test_map_type_unknown(self):
        """_map_type 未知类型返回 None"""
        assert LLMParser._map_type("unknown") is None
        assert LLMParser._map_type(None) is None

    def test_convert_with_full_data(self):
        """_convert 完整字段映射"""
        parser = LLMParser()

        # 模拟 MediaResult
        class FakeResult:
            title_en = "Test Title"
            title_cn = "测试标题"
            year = 2024
            season = 1
            end_season = 2
            episode = 3
            end_episode = 4
            resolution = "1080p"
            video_codec = "AVC"
            audio_codec = "AAC"
            release_group = "TestGroup"
            type = "anime"

        result = parser._convert(FakeResult())
        assert isinstance(result, ParserResult)
        assert result.title_en == "Test Title"
        assert result.title_cn == "测试标题"
        assert result.year == "2024"
        assert result.season == 1
        assert result.end_season == 2
        assert result.episode == 3
        assert result.end_episode == 4
        assert result.resource_pix == "1080p"
        assert result.video_encode == "AVC"
        assert result.audio_encode == "AAC"
        assert result.resource_team == "TestGroup"
        assert result.type == MediaType.ANIME
        assert result.confidence == 0.9

    def test_convert_with_minimal_data(self):
        """_convert 最小字段映射"""
        parser = LLMParser()

        class FakeResult:
            title_en = None
            title_cn = "测试"
            year = None
            season = None
            end_season = None
            episode = None
            end_episode = None
            resolution = None
            video_codec = None
            audio_codec = None
            release_group = None
            type = None

        result = parser._convert(FakeResult())
        assert result.title_cn == "测试"
        assert result.year is None
        assert result.season is None
        assert result.type is None

    def test_convert_none_input(self):
        """_convert 传入 None 返回 None"""
        parser = LLMParser()
        assert parser._convert(None) is None
