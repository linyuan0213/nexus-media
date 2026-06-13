"""Pagination utils 单元测试."""

from app.utils.pagination import get_page_range


class TestGetPageRange:
    def test_total_page_less_than_or_equal_5(self):
        assert list(get_page_range(1, 5)) == [1, 2, 3, 4, 5]
        assert list(get_page_range(3, 4)) == [1, 2, 3, 4]

    def test_current_page_near_start(self):
        assert list(get_page_range(1, 10)) == [1, 2, 3, 4, 5]
        assert list(get_page_range(3, 10)) == [1, 2, 3, 4, 5]

    def test_current_page_near_end(self):
        assert list(get_page_range(9, 10)) == [6, 7, 8, 9, 10]
        assert list(get_page_range(10, 10)) == [6, 7, 8, 9, 10]

    def test_current_page_in_middle(self):
        assert list(get_page_range(5, 10)) == [3, 4, 5, 6, 7]

    def test_total_page_zero(self):
        assert list(get_page_range(1, 0)) == []
