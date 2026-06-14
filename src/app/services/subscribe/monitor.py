"""订阅监控器 — 统一调度器，聚合 RSS 轮询、主动搜索、队列搜索三种策略."""

from __future__ import annotations

import datetime
from concurrent.futures import wait

import pytz

import log
from app.core.exceptions import DownloadError, IndexerError, MediaError, NetworkError, RepositoryError, ServiceError
from app.core.settings import settings
from app.domain.mediatypes import MediaType
from app.infrastructure.thread import ThreadExecutor
from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.search_engine import SubscribeSearchEngine
from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy
from app.services.subscribe_service import SubscribeService


class SubscriptionMonitor:
    """订阅监控器：统一调度器.

    职责：
    1. 按 queue_interval 周期执行队列搜索（高频）— 处理 state="D" 的订阅
    2. 按 rss_interval 周期执行 RSS 轮询（中频）— 处理 state="R" 的订阅
    3. 按 search_interval 周期执行主动搜索（低频）— 处理 state="R" 的订阅

    调度配置统一为：
    - subscribe.queue_interval — 队列搜索间隔（秒）
    - subscribe.rss_interval — RSS 轮询间隔（秒）
    - subscribe.search_interval — 主动搜索间隔（小时）
    """

    def __init__(
        self,
        subscribe_service: SubscribeService,
        thread_executor: ThreadExecutor,
        queue_strategy: QueueSearchStrategy,
        rss_strategy: RssFeedStrategy,
        indexer_strategy: IndexerSearchStrategy,
        coordinator: DownloadCoordinator | None = None,
    ):
        self._coordinator = coordinator
        self._subscribe = subscribe_service
        self._thread_executor = thread_executor
        self._queue_strategy = queue_strategy
        self._rss_strategy = rss_strategy
        self._indexer_strategy = indexer_strategy
        self._last_queue_run: datetime.datetime | None = None
        self._last_rss_run: datetime.datetime | None = None
        self._last_search_run: datetime.datetime | None = None
        self._tz = pytz.timezone(settings.tz)
        # 任务级去重：防止多个周期同时提交同一策略
        self._running_tasks: dict[str, bool] = {}
        self._bind_coordinator()

    def run(self) -> None:
        """统一入口，由定时服务调用.

        三种策略在满足各自周期时通过线程池并发执行，缩短整体耗时；
        各自更新 _last_*_run 时间戳。
        新增任务级去重，防止同一策略在上一次未结束时又被提交。
        """
        tasks = []
        if self._should_run_queue() and not self._running_tasks.get("queue"):
            self._running_tasks["queue"] = True
            tasks.append(self._thread_executor.submit(self._run_queue_search))
        if self._should_run_rss() and not self._running_tasks.get("rss"):
            self._running_tasks["rss"] = True
            tasks.append(self._thread_executor.submit(self._run_rss_feed))
        if self._should_run_search() and not self._running_tasks.get("search"):
            self._running_tasks["search"] = True
            tasks.append(self._thread_executor.submit(self._run_indexer_search))

        if tasks:
            wait(tasks)

    def _run_queue_search(self) -> None:
        try:
            log.info("[SubscriptionMonitor] 开始队列搜索...")
            self._queue_strategy.run()
            self._last_queue_run = datetime.datetime.now(self._tz)
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] 队列搜索失败: {e}")
        finally:
            self._running_tasks["queue"] = False

    def _run_rss_feed(self) -> None:
        try:
            log.info("[SubscriptionMonitor] 开始 RSS 轮询...")
            self._rss_strategy.run()
            self._last_rss_run = datetime.datetime.now(self._tz)
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] RSS 轮询失败: {e}")
        finally:
            self._running_tasks["rss"] = False

    def _run_indexer_search(self) -> None:
        try:
            log.info("[SubscriptionMonitor] 开始主动搜索...")
            self._indexer_strategy.run()
            self._last_search_run = datetime.datetime.now(self._tz)
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] 主动搜索失败: {e}")
        finally:
            self._running_tasks["search"] = False

    def _bind_coordinator(self) -> None:
        """将下载协调器绑定到各个搜索策略上."""
        if self._coordinator is None:
            return
        if hasattr(self._queue_strategy, "set_coordinator"):
            self._queue_strategy.set_coordinator(self._coordinator)
        if hasattr(self._indexer_strategy, "set_coordinator"):
            self._indexer_strategy.set_coordinator(self._coordinator)
        if hasattr(self._rss_strategy, "set_coordinator"):
            self._rss_strategy.set_coordinator(self._coordinator)

    def _should_run_queue(self) -> bool:
        """队列搜索：按 subscribe.queue_interval（秒）周期执行."""
        subscribe = settings.get("subscribe")
        if not subscribe:
            return True
        queue_interval = subscribe.get("queue_interval")
        if not queue_interval:
            return True
        try:
            queue_interval = int(queue_interval)
        except (ValueError, TypeError):
            return True
        if queue_interval <= 0:
            return True
        if self._last_queue_run is None:
            return True
        elapsed = (datetime.datetime.now(self._tz) - self._last_queue_run).total_seconds()
        return elapsed >= queue_interval

    def _should_run_rss(self) -> bool:
        """RSS 轮询：按 subscribe.rss_interval（秒）周期执行."""
        subscribe = settings.get("subscribe")
        if not subscribe:
            return False
        rss_interval = subscribe.get("rss_interval")
        if not rss_interval:
            return False
        try:
            rss_interval = int(rss_interval)
        except (ValueError, TypeError):
            return False
        if rss_interval <= 0:
            return False
        if self._last_rss_run is None:
            return True
        elapsed = (datetime.datetime.now(self._tz) - self._last_rss_run).total_seconds()
        return elapsed >= rss_interval

    def _should_run_search(self) -> bool:
        """主动搜索：按 subscribe.search_interval（小时）周期执行."""
        subscribe = settings.get("subscribe")
        if not subscribe:
            return False
        search_interval = subscribe.get("search_interval")
        if not search_interval:
            return False
        try:
            search_interval = int(search_interval)
        except (ValueError, TypeError):
            return False
        if search_interval <= 0:
            return False
        if self._last_search_run is None:
            return True
        elapsed = (datetime.datetime.now(self._tz) - self._last_search_run).total_seconds()
        return elapsed >= search_interval * 3600

    def trigger(self) -> None:
        """外部触发订阅监控（RSS 轮询 + 队列搜索 + 主动搜索）."""
        self.run()

    def refresh_subscription(self, mtype: str, rssid: str) -> None:
        """后台刷新单个订阅搜索。"""
        engine = SubscribeSearchEngine(
            indexer_strategy=self._indexer_strategy,
            queue_strategy=self._queue_strategy,
        )
        if MediaType.from_string(mtype) == MediaType.MOVIE:
            self._thread_executor.submit(engine.subscribe_search_movie, rssid)
        else:
            self._thread_executor.submit(engine.subscribe_search_tv, rssid)
