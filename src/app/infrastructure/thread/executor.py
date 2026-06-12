"""线程池执行器 — 通用异步任务调度。

特性：
- 可配置线程数
- 自动清理数据库 session（每个线程结束后调用 remove_session）
- 支持 submit / map / shutdown
- 优雅关闭（等待完成 + 超时强制关闭）
- 统计信息（活跃任务 / 已完成 / 队列大小）

用法：
    executor = ThreadExecutor(max_workers=50)
    executor.submit(my_func, arg1, arg2, kw=val)
    executor.map(my_func, iterable)
    executor.shutdown(wait=True, timeout=30)
"""

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor

from app.db.session import remove_session
from app.utils.exception_utils import ExceptionUtils


class ThreadExecutor:
    """线程池执行器.

    自托管单例：通过 named() 获取命名实例，shutdown_all() 统一关闭。
    """

    _instances: dict[str, "ThreadExecutor"] = {}
    _lock = threading.Lock()

    @classmethod
    def shutdown_all(cls) -> None:
        """关闭所有命名线程池（lifespan 清理用）."""
        for executor in list(cls._instances.values()):
            executor.shutdown(wait=False)
        cls._instances.clear()

    @classmethod
    def reset_instance(cls, name: str | None = None) -> None:
        """测试时重置指定或全部实例."""
        if name:
            if name in cls._instances:
                cls._instances[name].shutdown(wait=False)
                cls._instances.pop(name, None)
        else:
            cls.shutdown_all()

    def __init__(self, max_workers: int = 50, name: str = "default"):
        self._name = name
        self._max_workers = max_workers
        self._pool: ThreadPoolExecutor | None = None
        self._shutdown = False
        self._submitted: int = 0
        self._completed: int = 0
        self._lock = threading.Lock()

    @property
    def pool(self) -> ThreadPoolExecutor:
        if self._pool is None:
            import log

            self._pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix=f"nexus-{self._name}",
            )
            log.debug(f"[ThreadExecutor]创建线程池: {self._name} (workers={self._max_workers})")
        return self._pool

    @property
    def active_count(self) -> int:
        return self._submitted - self._completed

    @property
    def submitted_count(self) -> int:
        return self._submitted

    @property
    def completed_count(self) -> int:
        return self._completed

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """提交任务到线程池，返回 Future 对象."""
        if self._shutdown:
            raise RuntimeError(f"ThreadExecutor [{self._name}] 已关闭")

        def _wrapper(*w_args, **w_kwargs):
            try:
                return func(*w_args, **w_kwargs)
            except Exception:
                import log

                log.warn(f"[ThreadExecutor:{self._name}] 任务异常: {func.__name__}")
                ExceptionUtils.exception_traceback(Exception())
            finally:
                remove_session()
                with self._lock:
                    self._completed += 1

        with self._lock:
            self._submitted += 1
        return self.pool.submit(_wrapper, *args, **kwargs)

    def map(self, func: Callable, iterable: Iterator, timeout: float | None = None) -> Iterator:
        """并行执行 func 对 iterable 中每个元素，返回结果迭代器.

        底层使用 ThreadPoolExecutor.map，保持输入顺序。
        """
        if self._shutdown:
            raise RuntimeError(f"ThreadExecutor [{self._name}] 已关闭")

        submitted = len(list(iterable)) if hasattr(iterable, "__len__") else 0
        with self._lock:
            self._submitted += submitted

        def _wrapper(item):
            try:
                return func(item)
            except Exception:
                import log

                log.warn(f"[ThreadExecutor:{self._name}] map 任务异常: {func.__name__}")
                ExceptionUtils.exception_traceback(Exception())
                return None
            finally:
                remove_session()
                with self._lock:
                    self._completed += 1

        return self.pool.map(_wrapper, iterable, timeout=timeout)

    def shutdown(self, wait: bool = True, timeout: float | None = None):
        """关闭线程池.

        :param wait: 是否等待所有任务完成
        :param timeout: 等待超时秒数（wait=True 时默认 3 秒，防止进程阻塞）
        """
        self._shutdown = True
        if self._pool is None:
            return
        import log

        log.info(f"[ThreadExecutor]关闭线程池: {self._name} (active={self.active_count})")
        if wait:
            deadline = time.time() + (timeout if timeout is not None else 3.0)
            while self.active_count > 0 and time.time() < deadline:
                time.sleep(0.1)
            remaining = self.active_count
            if remaining > 0:
                log.info(f"[ThreadExecutor]线程池关闭超时: {self._name} (remaining={remaining})")
                self._pool.shutdown(wait=False, cancel_futures=True)
            else:
                self._pool.shutdown(wait=False)
        else:
            self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown(wait=True)
        return False

    def __del__(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)

    @classmethod
    def named(cls, name: str, max_workers: int = 50) -> "ThreadExecutor":
        """获取或创建命名线程池."""
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = cls(max_workers=max_workers, name=name)
            return cls._instances[name]
