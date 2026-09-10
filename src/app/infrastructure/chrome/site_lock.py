"""同站点浏览器串行锁（single-flight）.

同一站点（同会话键/指纹）并发触发过盾时，只需一个请求真正过盾；
其余请求等待后复用该会话已获得的 clearance Cookie，避免重复过盾。
"""

import threading
from contextlib import contextmanager

_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _meta_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


@contextmanager
def site_serial(key: str):
    """按站点会话键串行执行；不同站点互不影响。"""
    lock = _get_lock(key)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
