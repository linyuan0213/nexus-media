"""线程级超时工具.

Python 无法安全终止阻塞线程；这里用 daemon 线程隔离等待，超时后调用方立即
返回，线程本身仍会在自身 I/O 超时后退出。相比共享线程池，daemon 线程不会
占用池容量，也不会阻止进程退出。
"""

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


class HardTimeoutError(TimeoutError):
    """调用方等待超时；被调用线程可能仍在后台运行."""


def run_with_timeout(fn: Callable[[], T], timeout: float, *, name: str = "task") -> T:
    """在独立 daemon 线程执行 fn，最多等待 timeout 秒."""
    box: dict[str, Any] = {}
    done = threading.Event()

    def runner() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - 原样回传给等待方
            box["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=runner, name=f"{name}-timeout", daemon=True)
    thread.start()
    if not done.wait(timeout):
        raise HardTimeoutError(f"{name} 超时（{timeout:.1f}s）")
    if "error" in box:
        raise box["error"]
    return cast(T, box.get("value"))


def run_parallel_with_timeout(
    tasks: dict[str, Callable[[], T]],
    timeout: float,
) -> tuple[dict[str, T], set[str]]:
    """并行执行多个任务，返回（成功结果, 超时/失败任务名）."""
    results: dict[str, T] = {}
    finished: set[str] = set()
    failed: set[str] = set()
    lock = threading.Lock()

    def runner(task_name: str, fn: Callable[[], T]) -> None:
        try:
            value = fn()
            with lock:
                results[task_name] = value
        except Exception:  # noqa: BLE001 - 失败任务由超时/错误集合统一处理
            with lock:
                failed.add(task_name)
        finally:
            with lock:
                finished.add(task_name)

    threads = [
        threading.Thread(target=runner, args=(task_name, fn), name=f"{task_name}-timeout", daemon=True)
        for task_name, fn in tasks.items()
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    timed_out = set(tasks) - finished
    return results, timed_out | failed
