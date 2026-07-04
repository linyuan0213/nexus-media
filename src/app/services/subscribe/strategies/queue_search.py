"""队列搜索策略 — 处理 state='D' 的待处理订阅."""

import log
from app.domain.entities.rss import SubscribeState
from app.services.subscribe.strategies.base_search import BaseSearchStrategy
from app.services.subscribe.strategy_lock import strategy_lock


class QueueSearchStrategy(BaseSearchStrategy):
    """队列搜索策略：处理 state='D' 的待处理订阅.

    由 SubscriptionMonitor 每次 run 时调用，高频执行。
    负责将新添加的订阅从 D(待处理) 推进到 S(搜索中) 再到 R(监控中) 或 C(已完成)。
    """

    def run(self) -> None:
        """执行队列搜索，获取分布式锁防止并发，持锁期间自动续期."""
        with strategy_lock("subscribe:search:D", ttl_seconds=300) as acquired:
            if not acquired:
                log.info("[QueueSearchStrategy] 队列搜索正在执行，跳过")
                return
            self._search_movies(state=SubscribeState.PENDING.value)
            self._search_tvs(state=SubscribeState.PENDING.value)
