"""订阅策略包."""

from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy

__all__ = ["IndexerSearchStrategy", "QueueSearchStrategy", "RssFeedStrategy"]
