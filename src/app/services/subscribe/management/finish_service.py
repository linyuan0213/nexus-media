"""Subscribe finish service - 完成订阅."""

from typing import Any

import log
from app.domain.media_type_utils import MediaTypeMapper
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.constants import SUBSCRIBE_FINISHED
from app.events.payloads import SubscribeFinishedPayload
from app.services.subscribe.management.utils import tv_filter_signature


class SubscribeFinishService:
    """完成订阅服务"""

    def __init__(self, movie_repo, tv_repo, history_repo, message, event_bus, download_repo=None):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._history_repo = history_repo
        self._message = message
        self._event_bus = event_bus
        self._download_repo = download_repo

    def _finish_sibling_tvs(self, primary_row, media: Any, delete_subscribe_fn) -> None:
        """同媒体其他用户的订阅联动完成（共享媒体库已满足，ADR-021 5.4）"""
        try:
            siblings = self._tv_repo.get_all() or []
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Subscribe]查询兄弟订阅失败: {e}")
            return
        tmdb = str(getattr(primary_row, "TMDBID", None) or getattr(primary_row, "tmdb_id", "") or "")
        season = str(getattr(primary_row, "SEASON", None) or getattr(primary_row, "season", "") or "")
        primary_sig = tv_filter_signature(primary_row)
        for row in siblings:
            sid = getattr(row, "ID", None) or getattr(row, "id", None)
            if not sid or str(sid) == str(getattr(primary_row, "ID", "") or getattr(primary_row, "id", "")):
                continue
            row_tmdb = str(getattr(row, "TMDBID", None) or getattr(row, "tmdb_id", "") or "")
            row_season = str(getattr(row, "SEASON", None) or getattr(row, "season", "") or "")
            if row_tmdb != tmdb or (season and row_season != season):
                continue
            if getattr(row, "OVER_EDITION", None) or getattr(row, "over_edition", False):
                continue
            if tv_filter_signature(row) != primary_sig:
                continue
            log.info(f"[Subscribe]联动完成兄弟订阅 rssid={sid}（同一媒体共享下载）")
            delete_subscribe_fn(mtype=MediaType.TV, rssid=sid)

    def finish_rss_subscribe(self, rssid: int | None, media: Any, delete_subscribe_fn) -> None:
        """完成订阅"""
        if not rssid or not media:
            return
        rtype = MediaTypeMapper.to_tmdb(media.type)
        over_edition = False
        if media.type == MediaType.MOVIE:
            rss = self._movie_repo.get_all(rssid=rssid)
            if not rss:
                return
            owner_user_id = getattr(rss[0], "USER_ID", None)
            self._history_repo.upsert(
                rssid=rssid,
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
                user_id=owner_user_id,
            )
            delete_subscribe_fn(mtype=MediaType.MOVIE, rssid=rssid)
        else:
            rss = self._tv_repo.get_all(rssid=rssid)
            if not rss:
                return
            total = rss[0].TOTAL_EP
            over_edition = bool(rss[0].OVER_EDITION) if hasattr(rss[0], "OVER_EDITION") else False
            owner_user_id = getattr(rss[0], "USER_ID", None)
            self._history_repo.upsert(
                rssid=rssid,
                rtype=rtype,
                name=rss[0].NAME,
                year=rss[0].YEAR,
                season=rss[0].SEASON,
                tmdbid=rss[0].TMDBID,
                image=media.get_poster_image(),
                desc=media.overview,
                total=total,
                start=rss[0].CURRENT_EP,
                user_id=owner_user_id,
            )
            delete_subscribe_fn(mtype=MediaType.TV, rssid=rssid)
            self._finish_sibling_tvs(rss[0], media, delete_subscribe_fn)

        # 仅洗版订阅完成后清理下载历史（允许后续升级重下）；
        # 普通订阅保留下载历史，避免重新订阅时重复下载已完成的剧集
        if self._download_repo and media.tmdb_id and (media.type == MediaType.MOVIE or over_edition):
            season_prefix = media.get_season_string() if media.type != MediaType.MOVIE else None
            self._download_repo.delete_by_tmdb(media.tmdb_id, season_prefix)

        self._event_bus.publish(
            Event(
                event_type=SUBSCRIBE_FINISHED, payload=SubscribeFinishedPayload(media_info=media.to_dict(), rssid=rssid)
            )
        )
        log.info(
            f"[Subscribe]{media.type.value} {media.get_title_string()} "
            f"{media.get_season_string()} 订阅完成，删除订阅..."
        )
        self._message.send_rss_finished_message(media_info=media, owner_user_id=getattr(rss[0], "USER_ID", None))
