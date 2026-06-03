"""Subscribe finish service - 完成订阅."""

from typing import Any

import log
from app.events import Event
from app.events.constants import SUBSCRIBE_FINISHED
from app.domain.media_type_utils import MediaTypeMapper
from app.domain.mediatypes import MediaType


class SubscribeFinishService:
    """完成订阅服务"""

    def __init__(self, movie_repo, tv_repo, history_repo, message, event_bus):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._history_repo = history_repo
        self._message = message
        self._event_bus = event_bus

    def finish_rss_subscribe(self, rssid: int | None, media: Any, delete_subscribe_fn) -> None:
        """完成订阅"""
        if not rssid or not media:
            return
        rtype = MediaTypeMapper.to_tmdb(media.type)
        if media.type == MediaType.MOVIE:
            rss = self._movie_repo.get_all(rssid=rssid)
            if not rss:
                return
            self._history_repo.insert(
                rssid=str(rssid or ""),
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
            )
            delete_subscribe_fn(mtype=MediaType.MOVIE, rssid=rssid)
        else:
            rss = self._tv_repo.get_all(rssid=rssid)
            if not rss:
                return
            total = rss[0].TOTAL_EP
            self._history_repo.insert(
                rssid=str(rssid or ""),
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                season=rss[0].SEASON,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
                total=total,
                start=rss[0].CURRENT_EP,
            )
            delete_subscribe_fn(mtype=MediaType.TV, rssid=rssid)

        self._event_bus.publish(
            Event(event_type=SUBSCRIBE_FINISHED, payload={"media_info": media.to_dict(), "rssid": rssid})
        )
        log.info(
            f"[Subscribe]{media.type.value} {media.get_title_string()} {media.get_season_string()} 订阅完成，删除订阅..."
        )
        self._message.send_rss_finished_message(media_info=media)
