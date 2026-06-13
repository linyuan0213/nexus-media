"""NumberUtils 单元测试"""

from app.utils.number_utils import NumberUtils


class TestNumberUtils:
    def test_max_ele_a_empty(self):
        assert NumberUtils.max_ele("", "5") == 5

    def test_max_ele_b_empty(self):
        assert NumberUtils.max_ele("10", "") == 10

    def test_max_ele_both_empty(self):
        assert NumberUtils.max_ele("", "") == 0

    def test_max_ele_normal(self):
        assert NumberUtils.max_ele("3", "7") == 7

    def test_get_size_gb_zero(self):
        assert NumberUtils.get_size_gb(0) == 0.0

    def test_get_size_gb_none(self):
        assert NumberUtils.get_size_gb(None) == 0.0

    def test_get_size_gb_bytes(self):
        assert NumberUtils.get_size_gb(1024 * 1024 * 1024) == 1.0

    def test_format_byte_repr_bytes(self):
        assert NumberUtils.format_byte_repr(512) == "512 B"

    def test_format_byte_repr_kb(self):
        assert NumberUtils.format_byte_repr(2048) == "2.0 KB"

    def test_format_byte_repr_mb(self):
        assert NumberUtils.format_byte_repr(2 * 1024 * 1024) == "2.0 MB"

    def test_format_byte_repr_gb(self):
        assert NumberUtils.format_byte_repr(2 * 1024 * 1024 * 1024) == "2.0 GB"

    def test_format_byte_repr_tb(self):
        assert NumberUtils.format_byte_repr(2 * 1024 * 1024 * 1024 * 1024) == "2.0 TB"

    def test_format_byte_repr_str(self):
        assert NumberUtils.format_byte_repr("2048") == "2.0 KB"

    def test_format_byte_repr_invalid(self):
        assert NumberUtils.format_byte_repr("not_a_number") == "not_a_number"
