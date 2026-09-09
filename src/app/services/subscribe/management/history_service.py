"""Subscribe history service — 订阅历史记录管理."""

from app.db.repositories.subscribe_repo_adapter import SubscribeHistoryRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.schemas.auth import UserContext
from app.services.rss_processor import RssHelper
from app.services.subscribe_service import SubscribeService


class SubscribeHistoryService:
    """订阅历史服务 — 历史查询、删除、重做、清空."""

    def __init__(
        self,
        history_repo: SubscribeHistoryRepositoryAdapter,
        subscribe: SubscribeService,
        rss_helper: RssHelper,
    ):
        self._history_repo = history_repo
        self._subscribe = subscribe
        self._rss_helper = rss_helper

    def get_history(self, mtype: str, user: UserContext | None = None) -> list[dict]:
        """获取订阅历史记录（user 非空时按数据归属过滤）."""
        return [rec.to_dict() for rec in self._history_repo.get_all(rtype=mtype, user=user)]

    def delete(self, rssid: int | None, user: UserContext | None = None) -> None:
        """删除订阅历史记录（普通用户仅可删除自己的历史）."""
        if rssid is None:
            return
        if user is not None and not user.is_superadmin:
            if not self._history_repo.get_all(rid=rssid, user=user):
                return
        self._history_repo.delete(rssid)

    def redo(self, rssid: int | None, rtype: str, user: UserContext | None = None) -> tuple[int, str]:
        """从历史记录重新订阅（普通用户仅可重做自己的历史，新订阅归属该用户）."""
        if rssid is None:
            return -1, "缺少订阅ID"
        history = self._history_repo.get_all(rtype=rtype, rid=rssid, user=user)
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
            user_id=user.user_id if user else None,
        )
        return code, msg

    def truncate(self, user: UserContext | None = None) -> None:
        """清空订阅历史记录（普通用户仅清空自己的历史）."""
        if user is not None and not user.is_superadmin:
            for rec in self._history_repo.get_all(user=user):
                self._history_repo.delete(rec.id)
            return
        self._rss_helper.truncate_rss_history()
        self._subscribe.truncate_rss_episodes()
