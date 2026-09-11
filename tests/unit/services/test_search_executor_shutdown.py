"""搜索执行器关闭期容错测试.

应用退出/线程池关闭时提交任务会抛 RuntimeError，应静默跳过而不是让订阅处理报错。
"""

from unittest.mock import MagicMock, patch

from app.domain.enums import SearchType
from app.services.search_service import SearchExecutor


class _ClosedExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def submit(self, *args, **kwargs):
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")


class TestSearchExecutorShutdown:
    def test_submit_runtime_error_returns_empty(self):
        executor = SearchExecutor(max_workers=2)
        with patch("app.services.search_service.ThreadExecutor", _ClosedExecutor):
            result = executor.execute(
                search_func=MagicMock(return_value=[{"x": 1}]),
                search_names=["a", "b"],
                filter_args={},
                media_info=MagicMock(),
                in_from=SearchType.WEB,
            )
        assert result == []
