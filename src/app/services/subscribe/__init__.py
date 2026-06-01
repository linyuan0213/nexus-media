"""Subscribe service package — 订阅自动下载领域包.

包含：
- monitor: SubscriptionMonitor (统一调度器)
- coordinator: DownloadCoordinator (下载锁/防重)
- strategies: RSS 轮询、主动搜索、队列搜索三种策略
- management: 订阅 CRUD / 状态管理服务
"""

from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.management.service import SubscribeService
from app.services.subscribe.matcher import SubscribeMatcher
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy

__all__ = [
    "DownloadCoordinator",
    "IndexerSearchStrategy",
    "QueueSearchStrategy",
    "RssFeedStrategy",
    "SubscribeCalendarService",
    "SubscribeHistoryService",
    "SubscribeMatcher",
    "SubscribeService",
    "SubscriptionMonitor",
]
