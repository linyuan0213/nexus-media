"""站点搜索闸门：同一站点跨订阅、跨请求串行，避免并发触发站点流控."""

import threading
import time
from contextlib import contextmanager
from typing import Any

from app.infrastructure.distributed_lock.lock_manager import get_lock_manager

_DEFAULT_TIMEOUT = 30.0
_LOCK_TTL = 120


class SiteSearchBusyError(RuntimeError):
    """等待站点搜索许可超时."""


class SiteSearchGate:
    def __init__(self, lock_manager: Any | None = None):
        self._lock_manager = lock_manager or get_lock_manager()
        self._local_locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _local_lock(self, site_id: str) -> threading.Lock:
        with self._guard:
            lock = self._local_locks.get(site_id)
            if lock is None:
                lock = threading.Lock()
                self._local_locks[site_id] = lock
            return lock

    @contextmanager
    def acquire(self, site_id: Any, timeout: float = _DEFAULT_TIMEOUT):
        key = str(site_id or "").strip()
        if not key:
            yield
            return

        local = self._local_lock(key)
        deadline = time.monotonic() + max(0.0, timeout)
        if not local.acquire(timeout=max(0.0, timeout)):
            raise SiteSearchBusyError(f"站点 {key} 搜索繁忙")

        lock = None
        try:
            lock = self._lock_manager.create_lock(f"site:search:{key}", _LOCK_TTL)
            while not lock.acquire():
                # Redis/DB 锁后端不可用时，降级为进程内互斥，避免整轮搜索被 30s 超时拖死。
                if getattr(lock, "last_error", None) is not None:
                    lock = None
                    break
                if time.monotonic() >= deadline:
                    raise SiteSearchBusyError(f"站点 {key} 搜索繁忙")
                time.sleep(0.2)
            yield
        finally:
            if lock is not None:
                lock.release()
            local.release()


_gate: SiteSearchGate | None = None


def get_site_search_gate() -> SiteSearchGate:
    global _gate
    if _gate is None:
        _gate = SiteSearchGate()
    return _gate
