"""队列搜索策略 — 处理 state='D' 的待处理订阅."""

import log
from app.domain.entities.rss import SubscribeState
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.subscribe.strategies.base_search import BaseSearchStrategy


class QueueSearchStrategy(BaseSearchStrategy):
    """队列搜索策略：处理 state='D' 的待处理订阅.

    由 SubscriptionMonitor 每次 run 时调用，高频执行。
    负责将新添加的订阅从 D(待处理) 推进到 S(搜索中) 再到 R(监控中) 或 C(已完成)。
    """

    def run(self) -> None:
        """执行队列搜索，获取分布式锁防止并发."""
        dist_lock = get_lock_manager().create_lock("subscribe:search:D", ttl_seconds=1800)
        acquired = dist_lock.acquire()
        if not acquired:
            log.info("[QueueSearchStrategy] 队列搜索正在执行，跳过")
            return
        try:
            self._search_movies(state=SubscribeState.PENDING.value)
            self._search_tvs(state=SubscribeState.PENDING.value)
        finally:
            dist_lock.release()
