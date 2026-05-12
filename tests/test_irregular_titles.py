# -*- coding: utf-8 -*-
"""
影视标题解析器 — 不规则标题格式全面测试

测试覆盖：
1. 标准格式 (已支持)
2. 空格/横杠分隔格式
3. 圆括号/方括号包裹
4. 中文集数标注
5. 带点/单字母前缀
6. 单数字季集
7. 版本号/END后缀
8. 绝对集号
9. 合并季标注
"""
import sys
from unittest.mock import MagicMock
sys.modules['log'] = MagicMock()

import os
os.environ['NASTOOL_CONFIG'] = '/home/linyuan/python/config/config.yaml'

import pytest
from app.media.parser.video import parse_video_title
from app.utils.types import MediaType


# ============ 测试数据 ============

STANDARD_CASES = [
    # (title, expected_season, expected_episode, description)
    ("Show.S01E05.1080p.mkv", 1, 5, "标准 S01E05"),
    ("Show.S12E34.1080p.mkv", 12, 34, "双位数 S12E34"),
    ("Show.EP05.1080p.mkv", None, 5, "EP05"),
    ("Show.EP123.1080p.mkv", None, 123, "三位数 EP123"),
]

SPACE_SEPARATED_CASES = [
    ("Show S01E05 1080p.mkv", 1, 5, "空格分隔 S01E05"),
    ("Show S01 E05 1080p.mkv", 1, 5, "S和E之间空格"),
    ("Show - S01E05 - 1080p.mkv", 1, 5, "横杠包裹 S01E05"),
    ("Show S01 - E05 1080p.mkv", 1, 5, "S和E之间横杠"),
    ("Show S01 - 05 1080p.mkv", 1, 5, "S季横杠集号"),
]

BRACKET_CASES = [
    ("Show (05) 1080p.mkv", None, 5, "圆括号集号"),
    ("Show (S01E05) 1080p.mkv", 1, 5, "圆括号季集"),
    ("Show [05] 1080p.mkv", None, 5, "方括号集号"),
    ("Show [S01E05] 1080p.mkv", 1, 5, "方括号季集"),
    ("Show {05} 1080p.mkv", None, 5, "花括号集号"),
]

CHINESE_CASES = [
    ("作品名 第05集 1080p.mkv", None, 5, "第X集"),
    ("作品名 第5集 1080p.mkv", None, 5, "第X集 单位数"),
    ("作品名 第05话 1080p.mkv", None, 5, "第X话"),
    ("作品名 第05期 1080p.mkv", None, 5, "第X期"),
    ("作品名 第四季 第05集 1080p.mkv", 4, 5, "第四季第X集"),
    ("作品名 第一季 第1集 1080p.mkv", 1, 1, "第一季第1集"),
]

DOT_PREFIX_CASES = [
    ("Show EP.05 1080p.mkv", None, 5, "EP.05"),
    ("Show E.05 1080p.mkv", None, 5, "E.05"),
    ("Show E05 1080p.mkv", None, 5, "E05"),
]

SINGLE_DIGIT_CASES = [
    ("Show S1E5 1080p.mkv", 1, 5, "单数字 S1E5"),
    ("Show S01E5 1080p.mkv", 1, 5, "季双位集单位 S01E5"),
    ("Show S1E05 1080p.mkv", 1, 5, "季单位集双位 S1E05"),
]

VERSION_SUFFIX_CASES = [
    ("Show 05v2 1080p.mkv", None, 5, "v2版本后缀"),
    ("Show 05v3 1080p.mkv", None, 5, "v3版本后缀"),
    ("Show 05 END 1080p.mkv", None, 5, "END标记"),
    ("Show 05 END[1080p].mkv", None, 5, "END无空格"),
    ("Show 05 Fin 1080p.mkv", None, 5, "Fin标记"),
]

ABSOLUTE_EPISODE_CASES = [
    ("Show - 72 1080p.mkv", None, 72, "横杠绝对集号"),
    ("Show - 05 [1080p].mkv", None, 5, "横杠集号+方括号tag"),
    ("Show - 5 [1080p].mkv", None, 5, "横杠单位数集号"),
]

MERGED_SEASON_CASES = [
    ("[Group] Show 第四季 [04 - 总第70][1080p].mkv", 4, 4, "合并季标注"),
    ("[Group] Show 第四季 [04][1080p].mkv", 4, None, "仅季号方括号"),
]

SPECIAL_ANIME_CASES = [
    # 已测试过的真实案例
    ("[晚街与灯][Re：从零开始的异世界生活 第四季 / Re:Zero kara Hajimeru Isekai Seikatsu 4th Season][04 - 总第70][WebRip][1080P_AVC_AAC][简日双语内嵌]", 4, 4, "Re:Zero 合并季"),
    ("[ANi] Re：從零開始的異世界生活 第四季 - 05 [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4]", 4, 5, "Re:Zero ANi格式"),
    ("[LoliHouse] 关于我转生变成史莱姆这档事 / Tensei Shitara Slime Datta Ken  - 72 [WebRip 1080p HEVC-10bit AAC][简繁内封字幕][END]", None, 72, "Slime 绝对集号"),
    ("[DBD-Raws][关于我转生变成史莱姆这档事 第三季/Tensei Shitara Slime Datta Ken S3][01-24TV全集+SP+特典映像][1080P][BDRip][HEVC-10bit][FLAC][MKV](転生したらスライムだった件 S3)", 3, 1, "DBD-Raws 全季包"),
]

ALL_CASES = (
    STANDARD_CASES +
    SPACE_SEPARATED_CASES +
    BRACKET_CASES +
    CHINESE_CASES +
    DOT_PREFIX_CASES +
    SINGLE_DIGIT_CASES +
    VERSION_SUFFIX_CASES +
    ABSOLUTE_EPISODE_CASES +
    MERGED_SEASON_CASES +
    SPECIAL_ANIME_CASES
)


# ============ 测试类 ============

class TestStandardFormats:
    @pytest.mark.parametrize("title,season,episode,desc", STANDARD_CASES)
    def test_standard(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestSpaceSeparated:
    @pytest.mark.parametrize("title,season,episode,desc", SPACE_SEPARATED_CASES)
    def test_space_separated(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestBrackets:
    @pytest.mark.parametrize("title,season,episode,desc", BRACKET_CASES)
    def test_brackets(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestChineseFormats:
    @pytest.mark.parametrize("title,season,episode,desc", CHINESE_CASES)
    def test_chinese(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestDotPrefix:
    @pytest.mark.parametrize("title,season,episode,desc", DOT_PREFIX_CASES)
    def test_dot_prefix(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestSingleDigit:
    @pytest.mark.parametrize("title,season,episode,desc", SINGLE_DIGIT_CASES)
    def test_single_digit(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestVersionSuffix:
    @pytest.mark.parametrize("title,season,episode,desc", VERSION_SUFFIX_CASES)
    def test_version_suffix(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestAbsoluteEpisode:
    @pytest.mark.parametrize("title,season,episode,desc", ABSOLUTE_EPISODE_CASES)
    def test_absolute(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestMergedSeason:
    @pytest.mark.parametrize("title,season,episode,desc", MERGED_SEASON_CASES)
    def test_merged(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"


class TestSpecialAnime:
    @pytest.mark.parametrize("title,season,episode,desc", SPECIAL_ANIME_CASES)
    def test_special(self, title, season, episode, desc):
        info = parse_video_title(title)
        assert info.type == MediaType.TV, f"[{desc}] 应为TV类型"
        if season:
            assert info.begin_season == season, f"[{desc}] 期望季={season}, 实际={info.begin_season}"
        if episode:
            assert info.begin_episode == episode, f"[{desc}] 期望集={episode}, 实际={info.begin_episode}"
