"""订阅监控器 — 统一调度器，聚合 RSS 轮询、主动搜索、队列搜索三种策略."""

import datetime

import log
from app.core.exceptions import DownloadError, IndexerError, MediaError, NetworkError, RepositoryError, ServiceError
from app.core.settings import settings
from app.di import container
from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.search_engine import SubscribeSearchEngine
from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy


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
        queue_strategy: QueueSearchStrategy | None = None,
        rss_strategy: RssFeedStrategy | None = None,
        indexer_strategy: IndexerSearchStrategy | None = None,
        coordinator: DownloadCoordinator | None = None,
    ):
        self._coordinator = coordinator or DownloadCoordinator()
        self._queue_strategy = queue_strategy or QueueSearchStrategy(
            service=container.subscribe_service(),
            movie_repo=container.subscribe_service()._movie_repo,
            tv_repo=container.subscribe_service()._tv_repo,
            tv_episode_repo=container.subscribe_service()._tv_episode_repo,
            coordinator=self._coordinator,
        )
        self._rss_strategy = rss_strategy or RssFeedStrategy(
            subscribe=container.subscribe_service(),
            coordinator=self._coordinator,
        )
        self._indexer_strategy = indexer_strategy or IndexerSearchStrategy(
            service=container.subscribe_service(),
            movie_repo=container.subscribe_service()._movie_repo,
            tv_repo=container.subscribe_service()._tv_repo,
            tv_episode_repo=container.subscribe_service()._tv_episode_repo,
            coordinator=self._coordinator,
        )
        self._last_queue_run: datetime.datetime | None = None
        self._last_rss_run: datetime.datetime | None = None
        self._last_search_run: datetime.datetime | None = None

    def run(self) -> None:
        """统一入口，由定时服务调用.

        执行顺序：
        1. 队列搜索（按 queue_interval 间隔）
        2. RSS 轮询（按 rss_interval 间隔）
        3. 主动搜索（按 search_interval 间隔）
        """
        try:
            if self._should_run_queue():
                self._run_queue_search()
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] 队列搜索失败: {e}")

        try:
            if self._should_run_rss():
                self._run_rss_feed()
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] RSS 轮询失败: {e}")

        try:
            if self._should_run_search():
                self._run_indexer_search()
        except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
            log.error(f"[SubscriptionMonitor] 主动搜索失败: {e}")

    def _run_queue_search(self) -> None:
        log.info("[SubscriptionMonitor] 开始队列搜索...")
        self._queue_strategy.run()
        self._last_queue_run = datetime.datetime.now()

    def _run_rss_feed(self) -> None:
        log.info("[SubscriptionMonitor] 开始 RSS 轮询...")
        self._rss_strategy.run()
        self._last_rss_run = datetime.datetime.now()

    def _run_indexer_search(self) -> None:
        log.info("[SubscriptionMonitor] 开始主动搜索...")
        self._indexer_strategy.run()
        self._last_search_run = datetime.datetime.now()

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
        elapsed = (datetime.datetime.now() - self._last_queue_run).total_seconds()
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
        elapsed = (datetime.datetime.now() - self._last_rss_run).total_seconds()
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
        elapsed = (datetime.datetime.now() - self._last_search_run).total_seconds()
        return elapsed >= search_interval * 3600

    def trigger(self) -> None:
        """外部触发订阅监控（RSS 轮询 + 队列搜索 + 主动搜索）."""
        self.run()

    def refresh_subscription(self, mtype: str, rssid: str) -> None:
        """后台刷新单个订阅搜索."""
        engine = SubscribeSearchEngine(service=container.subscribe_service())
        if mtype == "MOV":
            container.thread_helper().start_thread(engine.subscribe_search_movie, (rssid,))
        else:
            container.thread_helper().start_thread(engine.subscribe_search_tv, (rssid,))
