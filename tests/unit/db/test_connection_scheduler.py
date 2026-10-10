"""数据库连接调度器（有界 FIFO 连接准入）测试."""

import threading
import time
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from app.db.connection_scheduler import (
    DbConnectionScheduler,
    DbConnectionTimeoutError,
    get_connection_scheduler,
    reset_connection_scheduler,
)
from app.db.session import SessionManager


@pytest.fixture(autouse=True)
def _isolate_scheduler():
    reset_connection_scheduler()
    yield
    reset_connection_scheduler()


class TestDbConnectionScheduler:
    def test_invalid_capacity_rejected(self):
        with pytest.raises(ValueError):
            DbConnectionScheduler(capacity=0)

    def test_acquire_release_tracks_in_flight(self):
        sched = DbConnectionScheduler(capacity=2, acquire_timeout=1)
        assert sched.in_flight == 0
        assert sched.waiting == 0

        with sched.acquire():
            assert sched.in_flight == 1
            assert sched.waiting == 1

        assert sched.in_flight == 0
        assert sched.waiting == 0

    def test_release_on_exception(self):
        sched = DbConnectionScheduler(capacity=1, acquire_timeout=1)
        with pytest.raises(RuntimeError):
            with sched.acquire():
                raise RuntimeError("boom")
        # 异常后许可已归还，仍可再次获取
        assert sched.in_flight == 0
        with sched.acquire():
            assert sched.in_flight == 1

    def test_capacity_exhaustion_times_out(self):
        sched = DbConnectionScheduler(capacity=1, acquire_timeout=0.2)
        outcome: dict[str, Any] = {}

        def _child():
            try:
                with sched.acquire():
                    outcome["acquired"] = True
            except DbConnectionTimeoutError:
                outcome["acquired"] = False

        with sched.acquire():
            worker = threading.Thread(target=_child)
            worker.start()
            worker.join(timeout=2)

        assert outcome["acquired"] is False
        assert sched.snapshot()["timeout_total"] == 1

    def test_reentrant_in_same_thread(self):
        sched = DbConnectionScheduler(capacity=1, acquire_timeout=0.5)
        with sched.acquire():
            assert sched.in_flight == 1
            # 同线程重入复用许可，不应阻塞或超时
            with sched.acquire():
                assert sched.in_flight == 1
            assert sched.in_flight == 1
        assert sched.in_flight == 0

    def test_child_thread_does_not_inherit_reentrancy(self):
        sched = DbConnectionScheduler(capacity=1, acquire_timeout=0.3)
        outcome: dict[str, Any] = {}

        def _child():
            try:
                with sched.acquire():
                    outcome["acquired"] = True
            except DbConnectionTimeoutError:
                outcome["acquired"] = False

        with sched.acquire():
            worker = threading.Thread(target=_child)
            worker.start()
            worker.join(timeout=2)
        # 子线程不共享父线程的重入深度，容量已满故应当超时
        assert outcome["acquired"] is False

    def test_fifo_order(self):
        sched = DbConnectionScheduler(capacity=1, acquire_timeout=3)
        order: list[int] = []
        threads: list[threading.Thread] = []

        def _worker(idx: int):
            with sched.acquire():
                order.append(idx)

        with sched.acquire():
            for idx in range(5):
                t = threading.Thread(target=_worker, args=(idx,))
                t.start()
                threads.append(t)
                time.sleep(0.05)  # 保证入队顺序确定

        for t in threads:
            t.join(timeout=3)

        assert order == [0, 1, 2, 3, 4]

    def test_snapshot_metrics(self):
        sched = DbConnectionScheduler(capacity=3, acquire_timeout=1)
        holding = threading.Semaphore(0)
        release = threading.Event()

        def _hold():
            with sched.acquire():
                holding.release()
                release.wait(timeout=2)

        threads = [threading.Thread(target=_hold) for _ in range(2)]
        for t in threads:
            t.start()

        assert holding.acquire(timeout=2)
        assert holding.acquire(timeout=2)
        # 两个线程均已持有许可
        snap = sched.snapshot()
        assert snap["in_flight"] == 2
        assert snap["available"] == 1
        assert snap["peak_in_flight"] == 2

        release.set()
        for t in threads:
            t.join(timeout=2)

        snap = sched.snapshot()
        assert snap["in_flight"] == 0
        assert snap["available"] == 3
        assert snap["acquired_total"] == 2


def _manager_with_factory(session) -> SessionManager:
    mgr = SessionManager.__new__(SessionManager)
    mgr._engine = cast(Any, object())
    mgr._factory = cast(Any, object())
    mgr._resolve_factory = lambda: lambda: session  # type: ignore[method-assign]
    return mgr


class TestSessionManagerGating:
    def test_session_scope_acquires_and_releases_permit(self):
        from app.db.connection_scheduler import configure_connection_scheduler

        configure_connection_scheduler(capacity=2, acquire_timeout=1)
        sched = get_connection_scheduler()
        mgr = _manager_with_factory(MagicMock())

        assert sched.in_flight == 0
        with mgr.session_scope() as db:
            assert db is not None
            assert sched.in_flight == 1
        assert sched.in_flight == 0

    def test_session_scope_releases_permit_on_error(self):
        from app.db.connection_scheduler import configure_connection_scheduler

        configure_connection_scheduler(capacity=2, acquire_timeout=1)
        sched = get_connection_scheduler()
        session = MagicMock()
        mgr = _manager_with_factory(session)

        with pytest.raises(RuntimeError):
            with mgr.session_scope():
                raise RuntimeError("boom")

        assert sched.in_flight == 0
        session.rollback.assert_called_once()
        session.close.assert_called_once()

    def test_transaction_scope_shares_single_permit(self):
        from app.db.connection_scheduler import configure_connection_scheduler

        configure_connection_scheduler(capacity=2, acquire_timeout=1)
        sched = get_connection_scheduler()
        session = MagicMock()
        mgr = _manager_with_factory(session)

        with mgr.transaction_scope() as tx:
            assert tx is session
            assert sched.in_flight == 1
            # 作用域内的 session_scope 复用共享 Session，不额外占用许可
            with mgr.session_scope():
                assert sched.in_flight == 1
        assert sched.in_flight == 0
        session.commit.assert_called_once()
        session.close.assert_called_once()
