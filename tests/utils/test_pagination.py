"""
Pagination Utils 测试
"""
from app.utils.pagination import get_page_range


class TestGetPageRange:
    """测试分页范围计算"""

    def test_total_page_less_than_5(self):
        """总页数 <= 5 时显示全部"""
        assert list(get_page_range(1, 3)) == [1, 2, 3]
        assert list(get_page_range(2, 5)) == [1, 2, 3, 4, 5]

    def test_current_page_near_start(self):
        """当前页 <= 3 时显示 1~5"""
        assert list(get_page_range(1, 10)) == [1, 2, 3, 4, 5]
        assert list(get_page_range(3, 10)) == [1, 2, 3, 4, 5]

    def test_current_page_near_end(self):
        """当前页 >= 总页数 - 2 时显示最后 5 页"""
        assert list(get_page_range(8, 10)) == [6, 7, 8, 9, 10]
        assert list(get_page_range(10, 10)) == [6, 7, 8, 9, 10]

    def test_current_page_in_middle(self):
        """当前页在中间时显示前后各 2 页"""
        assert list(get_page_range(5, 10)) == [3, 4, 5, 6, 7]
        assert list(get_page_range(6, 10)) == [4, 5, 6, 7, 8]

    def test_single_page(self):
        """只有 1 页"""
        assert list(get_page_range(1, 1)) == [1]

    def test_return_type_is_range(self):
        """返回类型为 range"""
        result = get_page_range(1, 5)
        assert isinstance(result, range)
