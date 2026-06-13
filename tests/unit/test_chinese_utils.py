"""Tests for app.utils.chinese_utils."""

import pytest

from app.utils.chinese_utils import to_simplified


class TestToSimplified:
    """Test suite for to_simplified utility."""

    def test_convert_traditional_to_simplified(self):
        assert to_simplified("繁體中文") == "繁体中文"

    def test_convert_hong_kong_to_simplified(self):
        assert to_simplified("髮型") == "发型"

    def test_already_simplified(self):
        assert to_simplified("简体中文") == "简体中文"

    def test_empty_string(self):
        assert to_simplified("") == ""

    def test_none_input(self):
        assert to_simplified(None) == ""

    def test_non_chinese_text(self):
        assert to_simplified("Hello World 123") == "Hello World 123"

    def test_mixed_text(self):
        assert to_simplified("電影 Movie 2024") == "电影 Movie 2024"

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("臺灣", "台湾"),
            ("軟體", "软件"),
            ("作業系統", "操作系统"),
            ("資料庫", "数据库"),
        ],
    )
    def test_common_conversions(self, input_text, expected):
        assert to_simplified(input_text) == expected
