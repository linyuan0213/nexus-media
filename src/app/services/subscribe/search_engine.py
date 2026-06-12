"""单媒体搜索 facade — 复用策略公共逻辑.

原 SubscribeSearchEngine 的内部方法已拆分至 strategies 包，
此类保留对外兼容的方法签名，但底层调用策略类实现.
"""

from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy


class SubscribeSearchEngine:
    """单媒体搜索 facade.

    职责：
    - subscribe_search_all() → IndexerSearchStrategy.run() (state="R")
    - subscribe_search(state="D") → QueueSearchStrategy.run()
    - subscribe_search_movie(rssid, state) → 直接调用策略 _search_movies
    - subscribe_search_tv(rssid, state) → 直接调用策略 _search_tvs
    """

    def __init__(
        self,
        indexer_strategy: IndexerSearchStrategy,
        queue_strategy: QueueSearchStrategy,
    ):
        self._indexer_strategy = indexer_strategy
        self._queue_strategy = queue_strategy

    def _get_indexer(self) -> IndexerSearchStrategy:
        return self._indexer_strategy

    def _get_queue(self) -> QueueSearchStrategy:
        return self._queue_strategy

    def subscribe_search_all(self) -> None:
        """主动搜索所有 state='R' 的订阅."""
        self._get_indexer().run()

    def subscribe_search(self, state: str = "D") -> None:
        """按状态搜索订阅."""
        if state == "R":
            self._get_indexer().run()
        else:
            self._get_queue().run()

    def subscribe_search_movie(self, rssid: int | None = None, state: str = "D") -> None:
        """搜索单个电影订阅."""
        if state == "R":
            self._get_indexer()._search_movies(state="R", rssid=rssid)
        else:
            self._get_queue()._search_movies(state="D", rssid=rssid)

    def subscribe_search_tv(self, rssid: int | None = None, state: str = "D") -> None:
        """搜索单个电视剧订阅."""
        if state == "R":
            self._get_indexer()._search_tvs(state="R", rssid=rssid)
        else:
            self._get_queue()._search_tvs(state="D", rssid=rssid)
