"""数据库连接调度器 — 基于有界 FIFO 许可队列的连接准入控制.

背景（issue #197）：应用存在多个彼此独立的 SQLAlchemy 连接池（API 池、调度池、
备份等临时引擎），叠加多套线程池后，同一时刻的在途连接总数可能超出数据库服务端
`max_connections`，表现为 `FATAL: remaining connection slots are reserved ...`。

方案：在"创建 session / 取用连接之前"统一排队。所有 session 创建前先取得一个全局
许可，session 关闭后归还许可，从而把**全进程在途连接数**限制在固定预算内：

- 许可通过 :class:`queue.Queue`（FIFO）发放，等待者按到达顺序有序获取，避免饥饿；
- `acquire()` 超时即快速失败，避免请求无限堆积把连接池拖垮；
- 支持同一线程重入（``threading.local`` 深度计数），避免同一逻辑流内嵌套获取导致自锁；
  线程本地变量不会被线程池的 contextvars 传播到子线程，因此子任务仍会各自排队计数。
"""

import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import log

# 全局连接预算默认值：需明显低于数据库 max_connections，为管理连接、迁移、
# 其他客户端及多 worker 进程留出余量。
DEFAULT_MAX_CONNECTIONS = 40
# 获取连接许可的超时（秒）：超时快速失败，避免请求无限堆积。
DEFAULT_ACQUIRE_TIMEOUT = 15
# 等待超过该阈值即记录告警（说明连接已接近饱和）。
_WAIT_WARN_THRESHOLD = 1.0


class DbConnectionTimeoutError(RuntimeError):
    """等待数据库连接许可超时（连接调度器已饱和）。"""


class DbConnectionScheduler:
    """有界 FIFO 数据库连接准入调度器."""

    def __init__(
        self,
        capacity: int = DEFAULT_MAX_CONNECTIONS,
        acquire_timeout: float = DEFAULT_ACQUIRE_TIMEOUT,
    ):
        if capacity < 1:
            raise ValueError("连接调度器容量必须 >= 1")
        self._capacity = int(capacity)
        self._acquire_timeout = float(acquire_timeout)
        # 预填 capacity 个许可：get() 获取、put() 归还，队列天然 FIFO
        self._permits: queue.Queue[int] = queue.Queue(maxsize=self._capacity)
        for token in range(self._capacity):
            self._permits.put_nowait(token)
        # 线程本地重入深度：仅在同一线程生效，不随线程池上下文传播到子线程
        self._local = threading.local()
        self._lock = threading.Lock()
        self._in_flight = 0
        self._peak_in_flight = 0
        self._acquired_total = 0
        self._timeout_total = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def acquire_timeout(self) -> float:
        return self._acquire_timeout

    @property
    def in_flight(self) -> int:
        """当前已持有的许可数（约等于在途连接数）."""
        with self._lock:
            return self._in_flight

    @property
    def waiting(self) -> int:
        """正在排队等待许可的调用方数量（含少量同线程重入）."""
        return self._capacity - self._permits.qsize()

    def snapshot(self) -> dict[str, float]:
        """调度器运行指标快照（观测 / 诊断用）."""
        with self._lock:
            return {
                "capacity": self._capacity,
                "acquire_timeout": self._acquire_timeout,
                "in_flight": self._in_flight,
                "available": self._permits.qsize(),
                "waiting": self._capacity - self._permits.qsize(),
                "peak_in_flight": self._peak_in_flight,
                "acquired_total": self._acquired_total,
                "timeout_total": self._timeout_total,
            }

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """获取一个数据库连接许可，退出时保证归还.

        同一线程可重入：重入时复用已持有的许可，不额外占用，也不提前释放。
        """
        depth = getattr(self._local, "depth", 0)
        if depth > 0:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth = depth
            return

        start = time.monotonic()
        try:
            token = self._permits.get(timeout=self._acquire_timeout)
        except queue.Empty as err:
            with self._lock:
                self._timeout_total += 1
                in_flight = self._in_flight
            raise DbConnectionTimeoutError(
                f"等待数据库连接许可超时（{self._acquire_timeout:.0f}s，容量 {self._capacity}，"
                f"在途 {in_flight}）；请降低并发或调大 DATABASE__MAX_CONNECTIONS"
            ) from err

        waited = time.monotonic() - start
        with self._lock:
            self._in_flight += 1
            self._acquired_total += 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)
            in_flight = self._in_flight
        if waited >= _WAIT_WARN_THRESHOLD:
            log.warn(
                f"[DbConnScheduler]连接许可等待 {waited:.2f}s（容量 {self._capacity}，在途 {in_flight}），"
                "数据库连接接近饱和"
            )

        self._local.depth = 1
        try:
            yield
        finally:
            self._local.depth = 0
            with self._lock:
                self._in_flight -= 1
            self._permits.put_nowait(token)


_scheduler: DbConnectionScheduler | None = None
_scheduler_lock = threading.Lock()


def get_connection_scheduler() -> DbConnectionScheduler:
    """获取全局连接调度器（惰性单例）."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = DbConnectionScheduler()
    return _scheduler


def configure_connection_scheduler(capacity: int, acquire_timeout: float) -> DbConnectionScheduler:
    """按配置重建全局连接调度器（启动期装配 / 测试使用）."""
    global _scheduler
    with _scheduler_lock:
        _scheduler = DbConnectionScheduler(capacity=capacity, acquire_timeout=acquire_timeout)
    return _scheduler


def reset_connection_scheduler() -> None:
    """重置全局连接调度器（测试使用）."""
    global _scheduler
    with _scheduler_lock:
        _scheduler = None
