"""线程级超时工具测试."""

import time

import pytest

from app.utils.timeout import HardTimeoutError, run_parallel_with_timeout, run_with_timeout


class TestRunWithTimeout:
    def test_returns_value(self):
        assert run_with_timeout(lambda: 42, 1.0) == 42

    def test_propagates_exception(self):
        def boom():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            run_with_timeout(boom, 1.0)

    def test_raises_on_timeout(self):
        start = time.monotonic()
        with pytest.raises(HardTimeoutError):
            run_with_timeout(lambda: time.sleep(0.5), 0.05)
        assert time.monotonic() - start < 0.3


class TestRunParallelWithTimeout:
    def test_collects_fast_and_times_out_slow_without_serial_wait(self):
        tasks = {
            "fast": lambda: "ok",
            "slow": lambda: time.sleep(0.5) or "slow",
        }
        start = time.monotonic()
        results, failed = run_parallel_with_timeout(tasks, 0.05)
        elapsed = time.monotonic() - start

        assert results == {"fast": "ok"}
        assert "slow" in failed
        assert elapsed < 0.3

    def test_failed_task_is_reported(self):
        def boom():
            raise RuntimeError("boom")

        results, failed = run_parallel_with_timeout({"bad": boom, "good": lambda: 1}, 1.0)

        assert results == {"good": 1}
        assert failed == {"bad"}
