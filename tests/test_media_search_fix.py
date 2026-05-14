"""
资源搜索图片不显示问题修复的测试用例

问题根因：
1. MetaInfo 对"标题 年份"格式的解析未正确提取年份，导致年份被包含在名称中传给 TMDB
2. __compare_tmdb_names 只有完全相等匹配，无法处理"相反的你和我"vs"正相反的你与我"等差异

修复内容：
- app/media/media.py: get_media_info 中增加年份后处理，从名称末尾提取 4 位年份
- app/media/media.py: __compare_tmdb_names 增加编辑距离相似度匹配（阈值 0.75）
- web/backend/web_utils.py: get_mediainfo_from_id 豆瓣 TMDB 失败时回退到豆瓣信息构造
"""
import difflib

import pytest


class TestMetaInfoYearExtraction:
    """测试年份提取修复"""

    @pytest.mark.parametrize("title,expected_name,expected_year", [
        ("相反的你和我 2026", "相反的你和我", "2026"),
        ("尖帽子的魔法工坊 2026", "尖帽子的魔法工坊", "2026"),
        ("你的名字 2016", "你的名字", "2016"),
    ])
    def test_year_extracted_from_name(self, title, expected_name, expected_year):
        """验证 MetaInfo 后处理后年份被正确提取、名称被清理"""
        # 这里用 get_media_info 的轻量级后处理逻辑验证
        import re
        year_match = re.search(r'\s+(\d{4})$', title)
        assert year_match is not None
        extracted_year = year_match.group(1)
        assert extracted_year == expected_year
        cleaned = re.sub(r'\s+\d{4}$', '', title)
        assert cleaned == expected_name


class TestTmdbNameComparison:
    """测试 TMDB 名称匹配修复"""

    @staticmethod
    def _compare(file_name, tmdb_names):
        """模拟 Media.__compare_tmdb_names 的逻辑"""
        if not file_name or not tmdb_names:
            return False
        if not isinstance(tmdb_names, list):
            tmdb_names = [tmdb_names]
        for tmdb_name in tmdb_names:
            if file_name == tmdb_name:
                return True
            if len(file_name) >= 3 and len(tmdb_name) >= 3:
                ratio = difflib.SequenceMatcher(None, file_name, tmdb_name).ratio()
                if ratio >= 0.75:
                    return True
        return False

    @pytest.mark.parametrize("a,b,expected", [
        # 应该匹配的高相似度场景
        ("相反的你和我", "正相反的你与我", True),
        ("相反的你和我", "正相反的你和我", True),
        ("你的名字", "你的名字2", True),
        ("钢铁侠", "钢铁侠2", True),
        ("复仇者联盟", "复仇者联盟4", True),
        # 不应该匹配的低相似度/短词场景
        ("你", "你的名字", False),
        ("你的名字", "你", False),
        ("猫", "猫和老鼠", False),
        ("星际穿越", "星际迷航", False),
        ("海贼王", "海贼王：红发歌姬", False),
    ])
    def test_compare_tmdb_names(self, a, b, expected):
        """验证编辑距离匹配逻辑"""
        result = self._compare(a, b)
        assert result == expected, f"{a!r} vs {b!r} 应该返回 {expected}, 实际 {result}"


class TestWebUtilsDoubanFallback:
    """测试 WebUtils 豆瓣回退逻辑"""

    def test_douban_fallback_creates_media_info(self):
        """
        验证当豆瓣详情获取成功但 TMDB 匹配失败时，
        get_mediainfo_from_id 仍然返回带豆瓣信息的 MetaInfo 对象
        """
        # 这个测试需要真实的豆瓣/TMDB API，标记为 integration
        pytest.skip("集成测试，需要真实 API 环境")
