"""
Pagination Utils - 分页工具函数

从 web.backend.web_utils.WebUtils 中下沉 get_page_range 方法，
使路由层不再依赖旧的 Flask 工具类。
"""

from collections.abc import Iterable


def get_page_range(current_page: int, total_page: int) -> Iterable[int]:
    """
    计算分页导航栏应显示的页码范围。

    规则：
    - 总页数 <= 5 时，显示全部页码。
    - 当前页 <= 3 时，显示 1~5。
    - 当前页 >= 总页数 - 2 时，显示最后 5 页。
    - 其他情况，以当前页为中心显示前后各 2 页。

    :param current_page: 当前页码（从 1 开始）
    :param total_page: 总页数
    :return: range(start_page, end_page + 1)
    """
    if total_page <= 5:
        start_page = 1
        end_page = total_page
    else:
        if current_page <= 3:
            start_page = 1
            end_page = 5
        elif current_page >= total_page - 2:
            start_page = total_page - 4
            end_page = total_page
        else:
            start_page = current_page - 2
            if total_page > current_page + 2:
                end_page = current_page + 2
            else:
                end_page = total_page
    return range(start_page, end_page + 1)
