"""测试电视剧识别改进"""

from app.media.parser.video import parse_video_title
from app.media.parser._release_groups import ReleaseGroupsMatcher
from app.utils.types import MediaType


class TestVideoParserFix:
    def test_bracket_episode(self):
        result = parse_video_title("[05] Title 1080p.mkv")
        assert result.begin_episode == 5
        assert result.type == MediaType.TV

    def test_bracket_episode_no_match_no_digits(self):
        result = parse_video_title("[abc] Title 1080p.mkv")
        assert result.begin_episode is None


class TestChineseSeasonDetection:
    def test_chinese_single_season(self):
        result = parse_video_title("Show 第2季")
        assert result.begin_season == 2
        assert result.type == MediaType.TV

    def test_chinese_season_range(self):
        result = parse_video_title("Show 第1-3季")
        assert result.begin_season == 1
        assert result.end_season == 3
        assert result.type == MediaType.TV

    def test_multitoken_chinese_season(self):
        result = parse_video_title("Show [1080p] 第1季")
        assert result.begin_season == 1


class TestChineseEpisodeDetection:
    def test_chinese_episode(self):
        result = parse_video_title("Show 第05集")
        assert result.begin_episode == 5
        assert result.type == MediaType.TV

    def test_chinese_episode_range(self):
        result = parse_video_title("Show 第01-05集")
        assert result.begin_episode is not None
        assert result.type == MediaType.TV

    def test_chinese_episode_with_tags(self):
        result = parse_video_title("Show [1080p] 第08集.mkv")
        assert result.begin_episode == 8


class TestWebSourceDetection:
    def test_amzn_source(self):
        result = parse_video_title("Show.S01E01.AMZN.WEB-DL.1080p")
        # AMZN 为 WEB 源标签，应被识别
        assert result.type == MediaType.TV

    def test_nf_source(self):
        result = parse_video_title("Show.S01E01.NF.WEB-DL.1080p")
        assert result.type == MediaType.TV


class TestSeasonEpisodeStandard:
    def test_standard_s01e01(self):
        result = parse_video_title("Show.S01E01.1080p")
        assert result.begin_season == 1
        assert result.begin_episode == 1
        assert result.type == MediaType.TV

    def test_bare_multi_episode_range(self):
        result = parse_video_title("Show.E01-E05.1080p")
        assert result.begin_episode == 1
        assert result.end_episode == 5

    def test_multi_season_pack(self):
        result = parse_video_title("Show.S01-S03.1080p.BluRay")
        assert result.begin_season == 1
        assert result.end_season == 3


class TestReleaseGroups:
    def test_ntb_group(self):
        m = ReleaseGroupsMatcher()
        result = m.match("[NTb] Show.S01E01.1080p")
        assert "NTb" in result

    def test_qxr_group(self):
        m = ReleaseGroupsMatcher()
        result = m.match("[QxR] Show.S01E01.1080p")
        assert "QxR" in result

    def test_rar_bg_group(self):
        m = ReleaseGroupsMatcher()
        result = m.match("[RARBG] Show.S01E01.1080p")
        assert "RARBG" in result

    def test_vcb_in_anime(self):
        m = ReleaseGroupsMatcher()
        result = m.match("[VCB-Studio] Anime [BDRip]")
        assert "VCB-Studio" in result
