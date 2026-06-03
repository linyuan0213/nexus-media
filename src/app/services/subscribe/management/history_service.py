"""Subscribe history service — 订阅历史记录管理."""

from app.db.repositories.subscribe_repo_adapter import SubscribeHistoryRepositoryAdapter
from app.di import container
from app.domain.mediatypes import MediaType


class SubscribeHistoryService:
    """订阅历史服务 — 历史查询、删除、重做、清空."""

    def __init__(self, history_repo=None, subscribe=None):
        self._history_repo = history_repo or SubscribeHistoryRepositoryAdapter()
        self._subscribe = subscribe or container.subscribe_service()

    def get_history(self, mtype: str) -> list[dict]:
        """获取订阅历史记录."""
        return [rec.to_dict() for rec in self._history_repo.get_all(rtype=mtype)]

    def delete(self, rssid: str) -> None:
        """删除订阅历史记录."""
        self._history_repo.delete(rssid)

    def redo(self, rssid: str, rtype: str) -> tuple[int, str]:
        """从历史记录重新订阅."""
        history = self._history_repo.get_all(rtype=rtype, rid=int(rssid) if rssid else None)
        if not history:
            return -1, "订阅历史记录不存在"
        mtype = MediaType.MOVIE if rtype == MediaType.MOVIE.value else MediaType.TV
        if history[0].season:
            season = int(str(history[0].season).replace("S", ""))
        else:
            season = None
        code, msg, _ = self._subscribe.add_rss_subscribe(
            mtype=mtype,
            name=history[0].name,
            year=history[0].year,
            channel="auto",
            season=season,
            mediaid=history[0].tmdb_id,
            total_ep=history[0].total,
            current_ep=history[0].start,
        )
        return code, msg

    def truncate(self) -> None:
        """清空订阅历史记录."""
        container.rss_helper().truncate_rss_history()
        self._subscribe.truncate_rss_episodes()
