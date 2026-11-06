"""站点搜索闸门并发测试."""

import threading
import time

import pytest

from app.sites.search_gate import SiteSearchBusyError, SiteSearchGate


class _Lock:
    def __init__(self):
        self.held = False

    def acquire(self):
        if self.held:
            return False
        self.held = True
        return True

    def release(self):
        self.held = False


class _LockManager:
    def __init__(self):
        self.lock = _Lock()

    def create_lock(self, _key, _ttl):
        return self.lock


def test_same_site_is_serialized():
    gate = SiteSearchGate(lock_manager=_LockManager())
    order = []

    def worker():
        with gate.acquire("mteam", timeout=2):
            order.append("start")
            time.sleep(0.2)
            order.append("end")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert order == ["start", "end", "start", "end"]


def test_wait_timeout_raises_busy():
    gate = SiteSearchGate(lock_manager=_LockManager())
    with gate.acquire("mteam", timeout=1):
        with pytest.raises(SiteSearchBusyError):
            with gate.acquire("mteam", timeout=0.01):
                pass
