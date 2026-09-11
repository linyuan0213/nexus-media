"""浏览器自动化并发闸门.

chrome 侧 BrowserPool 默认实例上限为 2，达到上限后复用现有实例（不再超建）。
这里在后端再加全局信号量：并发达到上限时阻塞等待，避免同时开启过多标签页把实例挤爆。
"""

import threading
from contextlib import contextmanager

from app.core.settings import settings

_DEFAULT_LIMIT = 2


def _resolve_limit() -> int:
    try:
        value = int((settings.get("laboratory") or {}).get("chrome_max_concurrency") or _DEFAULT_LIMIT)
    except (TypeError, ValueError):
        value = _DEFAULT_LIMIT
    return max(1, value)


_browser_semaphore = threading.BoundedSemaphore(_resolve_limit())


@contextmanager
def browser_slot():
    """获取一个浏览器并发槽位；占满时阻塞等待，退出时释放。"""
    _browser_semaphore.acquire()
    try:
        yield
    finally:
        _browser_semaphore.release()
