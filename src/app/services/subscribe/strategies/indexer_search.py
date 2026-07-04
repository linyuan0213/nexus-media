"""索引器搜索策略 — 处理 state='R' 的运行中订阅."""

import log
from app.domain.entities.rss import SubscribeState
from app.services.subscribe.strategies.base_search import BaseSearchStrategy
from app.services.subscribe.strategy_lock import strategy_lock


class IndexerSearchStrategy(BaseSearchStrategy):
    """索引器搜索策略：处理 state='R' 的运行中订阅.

    由 SubscriptionMonitor 按 search_interval 周期调用，低频执行。
    对已进入监控状态的订阅执行主动索引器搜索。
    """

    def run(self) -> None:
        """执行主动搜索，获取分布式锁防止并发，持锁期间自动续期."""
        with strategy_lock("subscribe:search:R", ttl_seconds=300) as acquired:
            if not acquired:
                log.info("[IndexerSearchStrategy] 主动搜索正在执行，跳过")
                return
            self._search_movies(state=SubscribeState.RUNNING.value)
            self._search_tvs(state=SubscribeState.RUNNING.value)
