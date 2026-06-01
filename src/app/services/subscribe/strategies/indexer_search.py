"""索引器搜索策略 — 处理 state='R' 的运行中订阅."""

import log
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.subscribe.strategies.base_search import BaseSearchStrategy


class IndexerSearchStrategy(BaseSearchStrategy):
    """索引器搜索策略：处理 state='R' 的运行中订阅.

    由 SubscriptionMonitor 按 search_interval 周期调用，低频执行。
    对已进入监控状态的订阅执行主动索引器搜索。
    """

    def run(self) -> None:
        """执行主动搜索，获取分布式锁防止并发."""
        dist_lock = get_lock_manager().create_lock("subscribe:search:R", ttl_seconds=1800)
        acquired = dist_lock.acquire()
        if not acquired:
            log.info("[IndexerSearchStrategy] 主动搜索正在执行，跳过")
            return
        try:
            self._search_movies(state="R")
            self._search_tvs(state="R")
        finally:
            dist_lock.release()
