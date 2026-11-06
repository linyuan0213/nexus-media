"""站点搜索闸门：同一站点跨订阅、跨请求串行，避免并发触发站点流控."""

import threading
import time
from contextlib import contextmanager
from typing import Any

from app.core.settings import settings
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager


class SiteSearchBusyError(RuntimeError):
    """等待站点搜索许可超时."""


class SiteSearchGate:
    def __init__(self, lock_manager: Any | None = None):
        self._lock_manager = lock_manager or get_lock_manager()
        self._local_locks: dict[str, threading.BoundedSemaphore] = {}
        self._guard = threading.Lock()
        self._deferred_at: dict[str, float] = {}
        self._deferred_guard = threading.Lock()

    @staticmethod
    def _config() -> tuple[int, float]:
        subscribe = settings.get("subscribe") or {}
        try:
            concurrency = max(1, int(subscribe.get("site_search_concurrency", 1) or 1))
        except (TypeError, ValueError):
            concurrency = 1
        try:
            timeout = max(0.1, float(subscribe.get("site_search_timeout", 30) or 30))
        except (TypeError, ValueError):
            timeout = 30.0
        return concurrency, timeout

    def _local_lock(self, site_id: str, concurrency: int) -> threading.BoundedSemaphore:
        with self._guard:
            lock = self._local_locks.get(site_id)
            if lock is None:
                lock = threading.BoundedSemaphore(concurrency)
                self._local_locks[site_id] = lock
            return lock

    def mark_deferred(self, site_id: Any) -> None:
        key = str(site_id or "").strip()
        if not key:
            return
        with self._deferred_guard:
            self._deferred_at[key] = time.time()

    def was_deferred_since(self, timestamp: float) -> bool:
        with self._deferred_guard:
            return any(value >= timestamp for value in self._deferred_at.values())

    @contextmanager
    def acquire(self, site_id: Any, timeout: float | None = None):
        key = str(site_id or "").strip()
        if not key:
            yield
            return

        concurrency, default_timeout = self._config()
        wait = default_timeout if timeout is None else max(0.1, timeout)
        deadline = time.monotonic() + wait
        local = self._local_lock(key, concurrency)
        if not local.acquire(timeout=wait):
            self.mark_deferred(key)
            raise SiteSearchBusyError(f"站点 {key} 搜索繁忙")

        locks: list[Any] = []
        try:
            backend_down = False
            while not locks and not backend_down:
                for slot in range(concurrency):
                    lock = self._lock_manager.create_lock(f"site:search:{key}:{slot}", 120)
                    if lock.acquire():
                        locks.append(lock)
                        break
                    if getattr(lock, "last_error", None) is not None:
                        backend_down = True
                        break
                if locks or backend_down:
                    break
                if time.monotonic() >= deadline:
                    self.mark_deferred(key)
                    raise SiteSearchBusyError(f"站点 {key} 搜索繁忙")
                time.sleep(0.2)
            yield
        finally:
            for lock in locks:
                lock.release()
            local.release()


_gate: SiteSearchGate | None = None


def get_site_search_gate() -> SiteSearchGate:
    global _gate
    if _gate is None:
        _gate = SiteSearchGate()
    return _gate
